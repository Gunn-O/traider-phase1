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
from agents.g4_sheets_logger import SheetsLogger

# Import utils
from utils import create_connector, PositionTracker

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

        # Connect with appropriate credentials
        if self.data_mode == 'simulate':
            # TradingView credentials
            tv_username = os.getenv('TV_USERNAME')
            tv_password = os.getenv('TV_PASSWORD')
            self.connector.connect(tv_username=tv_username, tv_password=tv_password)
        else:
            self.connector.connect()

        # Initialize agents
        print("🤖 Initializing agents...")
        self.g1_scanner = G1MarketScanner(config={'verbose': False})
        self.g2_analyzer = G2QuantAnalyzer(config={'verbose': False})
        self.g3_decision = G3MockDecisionAgent(config={'verbose': False})

        # Sheets Logger
        try:
            self.sheets_logger = SheetsLogger()
            if self.sheets_logger.enabled:
                print("✓ Google Sheets logging enabled")
        except Exception as e:
            print(f"⚠️  Sheets logger disabled: {e}")
            self.sheets_logger = None

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

        # Position Tracker (simulated)
        self.position_tracker = PositionTracker(max_total_positions=2)

        # Account state tracking (simple version for Phase I)
        self.account_state = {
            'balance': self.account_balance,
            'daily_pnl_pct': 0.0,
            'total_dd_pct': 0.0,
            'open_trades': 0,
            'news_active': False
        }

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

        # === Step 0: Update Positions (เช็คว่า positions เก่าปิดหรือยัง) ===
        print("🔄 Step 0: Update Open Positions...")
        market_data_temp = self.fetch_market_data()
        if market_data_temp:
            current_price = market_data_temp['current_price']
            # ดึง candle ล่าสุดเพื่อเอา high/low
            m5_df_temp = market_data_temp['m5_ohlcv']
            if m5_df_temp:
                latest = m5_df_temp[-1]
                self.position_tracker.update_positions(
                    current_price=current_price,
                    current_high=latest['high'],
                    current_low=latest['low']
                )

        summary = self.position_tracker.get_summary()
        print(f"   Open: {summary['open_positions']} | Closed: {summary['closed_positions']}")
        print(f"   Total P&L: ${summary['total_pnl']:,.2f}")
        if summary['open_conditions']:
            print(f"   Open Conditions: {', '.join(summary['open_conditions'])}")

        # === Step 1: Fetch Market Data ===
        print("\n📊 Step 1: Fetching market data...")
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

        # Update account_state with current open trades
        self.account_state['open_trades'] = len(self.position_tracker.open_positions)

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

        # === Position Check (ห้ามเปิด condition ซ้อน) ===
        print("\n🚫 Position Check...")

        can_open = self.position_tracker.can_open_new(condition)
        if not can_open:
            print(f"   ⏸️  BLOCKED: Cannot open {condition}")
            open_conditions = self.position_tracker.get_open_conditions()
            if condition in open_conditions:
                print(f"   Reason: Position {condition} already open")
            else:
                print(f"   Reason: Max positions reached ({len(open_conditions)}/2)")
            return

        print(f"   ✓ Can open new position for {condition}")

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

        # === Step 8: Log to Google Sheets ===
        print("\n📝 Step 8: Log to Google Sheets...")

        trade_id = None
        if self.sheets_logger and self.sheets_logger.enabled:
            # Generate trade_id
            trade_id = self.sheets_logger._generate_trade_id()
            decision['trade_id'] = trade_id

            # Log to sheets
            log_success = self.sheets_logger.log_trade(decision, world_state)
            if log_success:
                print(f"   ✓ Logged to Sheets: {trade_id}")
            else:
                print(f"   ⚠️  Failed to log to Sheets")
        else:
            print("   ⏸️  Sheets logging disabled")

        # === Add Position to Tracker ===
        print("\n📍 Step 9: Track Position...")
        position = self.position_tracker.add_position(decision)
        if position:
            print(f"   ✓ Position tracked: {position.id}")
            self.account_state['open_trades'] = len(self.position_tracker.open_positions)

            # Set callback to update Sheets when position closes
            if self.sheets_logger and self.sheets_logger.enabled and trade_id:
                def on_position_close(pos):
                    """Callback เมื่อ position ปิด"""
                    result = 'WIN' if pos.pnl > 0 else 'LOSS'
                    self.sheets_logger.update_trade_result(
                        trade_id=pos.trade_id,
                        result=result,
                        pnl_usd=pos.pnl,
                        close_reason=pos.close_reason
                    )

                position.on_close_callback = on_position_close
        else:
            print(f"   ⚠️  Failed to track position")

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
