#!/usr/bin/env python3
"""
ทดสอบว่า Position Tracking + Sheets Update ทำงานถูกต้อง

สร้าง fake position, simulate price hit TP, ตรวจสอบว่า Sheets update
"""

import os
from datetime import datetime
from dotenv import load_dotenv

from agents.g4_sheets_logger import SheetsLogger
from utils.position_tracker import PositionTracker

load_dotenv()


def test_position_close_workflow():
    """ทดสอบ workflow การปิด position และ update Sheets"""

    print("="*70)
    print("🧪 TEST: Position Close & Sheets Update")
    print("="*70)

    # Initialize
    logger = SheetsLogger()
    tracker = PositionTracker(max_total_positions=2)

    if not logger.enabled:
        print("\n❌ Sheets logging disabled!")
        print("   Set SHEETS_ENABLED=true in .env")
        return

    print(f"\n✅ Sheets enabled")

    # === Test 1: Create BUY position ===
    print(f"\n{'='*70}")
    print("1️⃣  Create BUY Position")
    print(f"{'='*70}")

    fake_decision = {
        'action': 'BUY',
        'condition': 'A3',
        'pattern': 'B3',
        'entry': 4650.0,
        'sl': 4640.0,
        'tp1': 4680.0,
        'tp2': 4690.0,
        'tp3': 4700.0,
        'lot_size': 0.5,
        'confidence': 0.82,
        'timestamp': datetime.now().isoformat()
    }

    fake_world_state = {
        'rsi': 38.5,
        'h1_trend': 'bullish',
        'session': 'London',
        'condition_name': 'ภูเขา',
        'pattern_name': 'แนวเด้ง'
    }

    # Generate trade_id (simulating main.py Step 8)
    trade_id = logger._generate_trade_id()
    fake_decision['trade_id'] = trade_id

    print(f"\n📝 Logging to Sheets...")
    print(f"   Trade ID: {trade_id}")
    print(f"   Action: {fake_decision['action']} {fake_decision['condition']}")
    print(f"   Entry: ${fake_decision['entry']:.2f}")
    print(f"   SL: ${fake_decision['sl']:.2f}, TP1: ${fake_decision['tp1']:.2f}")

    success = logger.log_trade(fake_decision, fake_world_state)

    if success:
        print(f"   ✅ Logged successfully!")
    else:
        print(f"   ❌ Failed to log")
        return

    # === Test 2: Track position with callback ===
    print(f"\n{'='*70}")
    print("2️⃣  Track Position with Callback")
    print(f"{'='*70}")

    position = tracker.add_position(fake_decision)
    print(f"\n✅ Position tracked: {position.id}")
    print(f"   Trade ID: {position.trade_id}")
    print(f"   Status: {'OPEN' if position.is_open else 'CLOSED'}")

    # Set callback (simulating main.py Step 9)
    def on_position_close(pos):
        """Callback เมื่อ position ปิด"""
        print(f"\n🔔 CALLBACK TRIGGERED for {pos.trade_id}")
        result = 'WIN' if pos.pnl > 0 else 'LOSS'
        print(f"   Result: {result}, P&L: ${pos.pnl:.2f}, Reason: {pos.close_reason}")

        success = logger.update_trade_result(
            trade_id=pos.trade_id,
            result=result,
            pnl_usd=pos.pnl,
            close_reason=pos.close_reason
        )

        if success:
            print(f"   ✅ Sheets updated!")
        else:
            print(f"   ❌ Failed to update Sheets")

    position.on_close_callback = on_position_close

    # === Test 3: Simulate price movement (hit TP1) ===
    print(f"\n{'='*70}")
    print("3️⃣  Simulate Price Hit TP1")
    print(f"{'='*70}")

    print(f"\n💰 Price movement:")
    print(f"   Entry: 4650 → Current: 4680")
    print(f"   Candle High: 4682 (> TP1 at 4680)")

    # Update positions (should trigger TP1)
    tracker.update_positions(
        current_price=4680.0,
        current_high=4682.0,
        current_low=4675.0
    )

    # Check status
    summary = tracker.get_summary()
    print(f"\n📊 Summary after update:")
    print(f"   Open: {summary['open_positions']}")
    print(f"   Closed: {summary['closed_positions']}")
    print(f"   Total P&L: ${summary['total_pnl']:,.2f}")
    print(f"   Win Rate: {summary['win_rate']:.1f}%")

    # === Verify ===
    print(f"\n{'='*70}")
    print("4️⃣  VERIFY in Google Sheets")
    print(f"{'='*70}")

    sheets_id = os.getenv('GOOGLE_SHEETS_ID')
    print(f"\n🔗 Check Google Sheets:")
    print(f"   https://docs.google.com/spreadsheets/d/{sheets_id}")
    print(f"\n📋 Look for trade_id: {trade_id}")
    print(f"   Expected result: WIN")
    print(f"   Expected P&L: $150.00")
    print(f"   Expected close_reason: TP1")

    print(f"\n{'='*70}")
    print("✅ TEST COMPLETED!")
    print(f"{'='*70}")


if __name__ == "__main__":
    test_position_close_workflow()
