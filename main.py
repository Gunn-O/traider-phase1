#!/usr/bin/env python3
"""
Tra(i)der Phase I - Main Trading Loop

รัน pipeline G1→G2→G3→G4 ทุก 5 นาที (ตาม M5 candle close)
- DATA_MODE=simulate: yfinance near real-time data
- ถ้ามี signal → ส่ง LINE
- ถ้าไม่มี → รอ candle ถัดไป

Usage:
    python main.py
"""

import os
import time
import schedule
from datetime import datetime, timedelta
from typing import Optional, Dict
from dotenv import load_dotenv

# Import agents
from agents.g1_signal_logic import G1MarketScanner
from agents.g2_quant_analysis import G2QuantAnalyzer
from agents.g3_decision_mock import G3MockDecisionAgent
from agents.g3_money_management import calculate_lot_size
from agents.g3_risk_gate import guardian_check
from agents.g4_notify import notify_signal

# Import utils
from utils import create_connector

# Load environment
load_dotenv()


class TraiderMainLoop:
    """Main trading loop for Tra(i)der Phase I"""

    def __init__(self):
        """Initialize trading system"""

        # Configuration
        self.data_mode = os.getenv('DATA_MODE', 'simulate')
        self.symbol = os.getenv('BACKTEST_SYMBOL', 'XAUUSD')
        self.account_balance = float(os.getenv('ACCOUNT_BALANCE', '10000'))
        self.risk_pct = float(os.getenv('RISK_PCT', '1.5'))

        print("="*70)
        print("🤖 Tra(i)der Phase I - AI Trading System")
        print("="*70)
        print(f"Mode: {self.data_mode}")
        print(f"Symbol: {self.symbol}")
        print(f"Account Balance: ${self.account_balance:,.2f}")
        print(f"Risk per Trade: {self.risk_pct}%")
        print("="*70)

        # Initialize data connector
        print(f"\n📡 Initializing data connector ({self.data_mode} mode)...")
        self.connector = create_connector(self.data_mode)
        self.connector.connect()

        # Initialize agents
        print("🤖 Initializing agents...")
        self.g1_scanner = G1MarketScanner(config={'verbose': False})
        self.g2_analyzer = G2QuantAnalyzer(config={'verbose': False})
        self.g3_decision = G3MockDecisionAgent(config={'verbose': False})

        # Risk profile
        self.risk_profile = {
            'risk_per_trade_pct': self.risk_pct,
            'min_lot': 0.01,
            'max_lot': 1.00,
            'max_dd_pct': 5.0,
            'max_daily_loss_pct': 3.0,
            'max_open_trades': 2,
            'min_confidence': 0.70,
            'min_rr_ratio': 1.2
        }

        # Account state tracking (simple version for Phase I)
        self.account_state = {
            'balance': self.account_balance,
            'daily_pnl_pct': 0.0,
            'total_dd_pct': 0.0,
            'open_trades': 0,
            'news_active': False
        }

        # Anti-clustering: ป้องกันส่ง signal ซ้ำๆ
        self.last_signal_time = None  # เวลาที่ส่ง signal ล่าสุด
        self.signal_cooldown_minutes = 30  # ห่างกัน 30 นาทีขึ้นไป
        self.last_signal_condition = None  # condition ล่าสุดที่ส่ง

        print("✓ System initialized\n")

    def fetch_market_data(self) -> Optional[Dict]:
        """
        ดึงข้อมูล M5 และ H1 candles

        Returns:
            market_data dict หรือ None ถ้าดึงไม่สำเร็จ
        """
        try:
            # ดึง M5 candles (80 แท่ง)
            m5_df = self.connector.get_candles(
                symbol=self.symbol,
                timeframe=5,
                count=80
            )

            # ดึง H1 candles (20 แท่ง)
            h1_df = self.connector.get_candles(
                symbol=self.symbol,
                timeframe=60,
                count=20
            )

            if m5_df.empty or h1_df.empty:
                print("⚠️  No data available")
                return None

            # Get current price (last close)
            current_price = float(m5_df.iloc[-1]['close'])

            # Build market_data dict
            market_data = {
                'm5_ohlcv': m5_df.to_dict('records'),
                'h1_candles': h1_df.to_dict('records'),
                'current_price': current_price,
                'timestamp': datetime.now().isoformat(),
                'symbol': self.symbol
            }

            return market_data

        except Exception as e:
            print(f"❌ Error fetching data: {e}")
            return None

    def run_pipeline(self):
        """
        รัน trading pipeline: G1 → G2 → G3 → G4

        Pipeline:
        1. G1: Scan market conditions
        2. G2: Calculate confidence score
        3. G3a: Make decision (BUY/SELL/SKIP)
        3. G3b: Calculate lot size
        4. G3c: Guardian check (risk gate)
        5. G4: Send LINE notification
        """

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"\n{'='*70}")
        print(f"🔄 Pipeline Run - {timestamp}")
        print(f"{'='*70}")

        # === Step 1: Fetch Market Data ===
        print("📊 Step 1: Fetching market data...")
        market_data = self.fetch_market_data()

        if not market_data:
            print("⏸️  No data - skipping this cycle")
            return

        price = market_data['current_price']
        print(f"   Current Price: ${price:,.2f}")

        # === Step 2: G1 Market Scanning ===
        print("\n🔍 Step 2: G1 Market Scanning...")
        world_state = self.g1_scanner.scan_conditions(market_data)

        if not world_state:
            print("   ⏸️  No valid conditions detected - SKIP")
            return

        condition = world_state.get('condition_candidate', 'N/A')
        print(f"   ✓ Condition: {condition}")
        print(f"   RSI: {world_state.get('rsi', 0):.1f}")
        print(f"   Nearest S/R: ${world_state.get('nearest_sr', 0):.2f}")

        # === Step 3: G2 Quantitative Analysis ===
        print("\n📈 Step 3: G2 Quantitative Analysis...")
        confidence_data = self.g2_analyzer.analyze(world_state)

        if not confidence_data:
            print("   ⏸️  Confidence too low - SKIP")
            return

        confidence = confidence_data.get('confidence', 0)
        print(f"   ✓ Confidence: {confidence:.3f}")

        # === Step 4: G3a Decision ===
        print("\n🎯 Step 4: G3 Decision Making...")
        decision = self.g3_decision.decide(world_state, confidence_data)

        if not decision:
            print("   ⏸️  No valid decision - SKIP")
            return

        action = decision.get('action', 'SKIP')
        entry = decision.get('entry', 0)
        sl = decision.get('sl', 0)
        tp1 = decision.get('tp1', 0)

        print(f"   ✓ Action: {action}")
        print(f"   Entry: ${entry:.2f}")
        print(f"   SL: ${sl:.2f}")
        print(f"   TP1: ${tp1:.2f}")

        if action == 'SKIP':
            print("   ⏸️  Decision is SKIP")
            return

        # === Step 5: G3b Money Management ===
        print("\n💰 Step 5: Calculate Lot Size...")
        lot_size = calculate_lot_size(
            decision=decision,
            account_balance=self.account_balance,
            risk_profile=self.risk_profile
        )

        decision['lot_size'] = lot_size
        print(f"   ✓ Lot Size: {lot_size}")

        # === Step 6: G3c Guardian Check ===
        print("\n🛡️  Step 6: Guardian Risk Check...")
        guardian_result = guardian_check(
            decision=decision,
            lot=lot_size,
            account_state=self.account_state,
            risk_profile=self.risk_profile
        )

        if not guardian_result.get('approved'):
            reason = guardian_result.get('reason', 'Unknown')
            print(f"   ❌ BLOCKED: {reason}")
            return

        print("   ✓ Risk check passed")

        # === Anti-Clustering Check ===
        print("\n🚫 Anti-Clustering Check...")

        # ตรวจสอบว่าส่ง signal ไปเมื่อไหร่
        if self.last_signal_time:
            time_since_last = (datetime.now() - self.last_signal_time).total_seconds() / 60
            if time_since_last < self.signal_cooldown_minutes:
                print(f"   ⏸️  BLOCKED: Signal sent {time_since_last:.1f} min ago")
                print(f"   Cooldown: {self.signal_cooldown_minutes} min")
                return

        # ตรวจสอบว่าเป็น condition เดิมหรือไม่ (ภายใน 1 ชั่วโมง)
        if self.last_signal_time and self.last_signal_condition == condition:
            time_since_last = (datetime.now() - self.last_signal_time).total_seconds() / 60
            if time_since_last < 60:  # ภายใน 1 ชั่วโมง
                print(f"   ⏸️  BLOCKED: Same condition ({condition}) within 1 hour")
                return

        print("   ✓ Anti-clustering check passed")

        # === Step 7: G4 Notification ===
        print("\n📱 Step 7: Send LINE Notification...")

        # Add metadata for notification
        decision['confidence'] = confidence
        decision['condition'] = condition
        decision['condition_name'] = world_state.get('condition_name', '')
        decision['reasoning'] = decision.get('reasoning', 'Rule-based decision')
        decision['trend_h1'] = world_state.get('h1_trend', '')
        decision['session'] = world_state.get('session', '')

        # Send notification
        notify_success = notify_signal(decision)

        if notify_success:
            print("   ✓ LINE notification sent")
        else:
            print("   ⚠️  LINE notification disabled or failed")

        # Update tracking (ป้องกัน signal ซ้ำ)
        self.last_signal_time = datetime.now()
        self.last_signal_condition = condition
        self.account_state['open_trades'] += 1  # เพิ่มจำนวน open trades

        # === Summary ===
        print(f"\n{'='*70}")
        print(f"✅ SIGNAL GENERATED")
        print(f"{'='*70}")
        print(f"   {action} {condition}")
        print(f"   Entry: ${entry:.2f} | SL: ${sl:.2f} | TP1: ${tp1:.2f}")
        print(f"   Lot: {lot_size} | Confidence: {confidence:.1%}")
        print(f"{'='*70}\n")

    def start(self):
        """
        เริ่มต้น trading loop

        รันทันที 1 ครั้ง แล้วตั้งเวลารันทุก 5 นาที
        """

        print("\n🚀 Starting trading loop...")
        print("⏰ Running every 5 minutes (M5 candle close)")
        print("Press Ctrl+C to stop\n")

        # Run immediately
        self.run_pipeline()

        # Schedule to run every 5 minutes
        schedule.every(5).minutes.do(self.run_pipeline)

        # Main loop
        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\n🛑 Stopping trading loop...")
            print("Goodbye! 👋\n")
            self.connector.disconnect()


def main():
    """Main entry point"""

    # Validate environment
    data_mode = os.getenv('DATA_MODE', 'simulate')

    if data_mode not in ['backtest', 'simulate', 'live']:
        print(f"❌ Invalid DATA_MODE: {data_mode}")
        print("   Set DATA_MODE to 'backtest', 'simulate', or 'live' in .env")
        return

    if data_mode == 'live':
        print("⚠️  Live trading is Phase II feature")
        print("   For Phase I, use DATA_MODE=simulate")

        response = input("\nContinue anyway? (y/n): ")
        if response.lower() != 'y':
            return

    # Create and start trading loop
    trader = TraiderMainLoop()
    trader.start()


if __name__ == "__main__":
    main()
