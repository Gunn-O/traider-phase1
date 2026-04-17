#!/usr/bin/env python3
"""
ทดสอบ Sheets Logging + Position Tracking

สร้าง fake signal เพื่อทดสอบว่า:
1. Log เข้า Sheets ได้ไหม
2. Update result เมื่อปิด position
"""

import os
from datetime import datetime
from dotenv import load_dotenv

from agents.g4_sheets_logger import SheetsLogger
from utils.position_tracker import PositionTracker

load_dotenv()

def test_full_workflow():
    """ทดสอบ workflow เต็มรูปแบบ"""

    print("="*70)
    print("🧪 TEST: Sheets Logging + Position Tracking")
    print("="*70)

    # Initialize
    logger = SheetsLogger()
    tracker = PositionTracker(max_total_positions=2)

    if not logger.enabled:
        print("\n❌ Sheets logging disabled!")
        print("   Set SHEETS_ENABLED=true in .env")
        return

    print(f"\n✅ Sheets logging enabled")

    # === Test 1: Log BUY Signal ===
    print(f"\n{'='*70}")
    print("1️⃣  TEST: Log BUY Signal")
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

    # Generate trade_id
    trade_id = logger._generate_trade_id()
    fake_decision['trade_id'] = trade_id

    print(f"\n📝 Logging to Sheets...")
    print(f"   Trade ID: {trade_id}")
    print(f"   Action: BUY A3 ภูเขา")
    print(f"   Entry: ${fake_decision['entry']:.2f}")

    success = logger.log_trade(fake_decision, fake_world_state)

    if success:
        print(f"   ✅ Logged successfully!")
    else:
        print(f"   ❌ Failed to log")
        return

    # === Test 2: Track Position ===
    print(f"\n{'='*70}")
    print("2️⃣  TEST: Track Position")
    print(f"{'='*70}")

    position = tracker.add_position(fake_decision)
    print(f"\n✅ Position tracked: {position.id}")
    print(f"   Status: {'OPEN' if position.is_open else 'CLOSED'}")

    # Set callback to update Sheets when position closes
    def on_position_close(pos):
        """Callback เมื่อ position ปิด"""
        result = 'WIN' if pos.pnl > 0 else 'LOSS'
        logger.update_trade_result(
            trade_id=pos.trade_id,
            result=result,
            pnl_usd=pos.pnl,
            close_reason=pos.close_reason
        )

    position.on_close_callback = on_position_close

    # === Test 3: Simulate TP Hit ===
    print(f"\n{'='*70}")
    print("3️⃣  TEST: Simulate TP1 Hit")
    print(f"{'='*70}")

    print(f"\n💰 Simulating price movement...")
    print(f"   Price: 4650 → 4680 (hit TP1)")

    # Update positions (simulate price hit TP1)
    tracker.update_positions(
        current_price=4680.0,
        current_high=4682.0,
        current_low=4675.0
    )

    summary = tracker.get_summary()
    print(f"\n📊 Summary:")
    print(f"   Open: {summary['open_positions']}")
    print(f"   Closed: {summary['closed_positions']}")
    print(f"   Total P&L: ${summary['total_pnl']:,.2f}")
    print(f"   Win Rate: {summary['win_rate']:.1f}%")

    # === Test 4: Verify in Sheets ===
    print(f"\n{'='*70}")
    print("4️⃣  VERIFY: Check Google Sheets")
    print(f"{'='*70}")

    sheets_id = os.getenv('GOOGLE_SHEETS_ID')
    print(f"\n🔗 Open Google Sheets:")
    print(f"   https://docs.google.com/spreadsheets/d/{sheets_id}")
    print(f"\n📋 Look for:")
    print(f"   Trade ID: {trade_id}")
    print(f"   Result: WIN")
    print(f"   P&L: $150.00")
    print(f"   Close Reason: TP1")

    print(f"\n{'='*70}")
    print("✅ TEST COMPLETED!")
    print(f"{'='*70}")


if __name__ == "__main__":
    test_full_workflow()
