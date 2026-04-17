#!/usr/bin/env python3
"""
ทดสอบ Position Tracking - Force signal เพื่อทดสอบ

จำลองสถานการณ์:
1. ส่ง signal A3 BUY @ 4720
2. ลองส่ง A3 ซ้ำ → ควรถูกบล็อค (position ยังเปิดอยู่)
3. ราคาไป hit TP1 → position ปิด
4. ส่ง A3 ใหม่ → ควรส่งได้ (position เก่าปิดแล้ว)
"""

from utils.position_tracker import PositionTracker
from datetime import datetime

def test_position_tracking():
    print("="*70)
    print("🧪 POSITION TRACKING TEST")
    print("="*70)

    tracker = PositionTracker(max_total_positions=2)

    # === Test 1: เปิด position A3 ===
    print("\n1️⃣  Open position A3 BUY @ 4720")
    signal_a3 = {
        'action': 'BUY',
        'condition': 'A3',
        'entry': 4720.0,
        'sl': 4710.0,
        'tp1': 4750.0,
        'tp2': 4760.0,
        'tp3': 4770.0,
        'lot_size': 0.5,
        'timestamp': datetime.now().isoformat()
    }

    can_open = tracker.can_open_new('A3')
    print(f"   Can open A3? {can_open}")

    if can_open:
        pos = tracker.add_position(signal_a3)
        print(f"   ✓ Position opened: {pos.id}")
    else:
        print("   ✗ Cannot open")

    summary = tracker.get_summary()
    print(f"   Open positions: {summary['open_positions']}")

    # === Test 2: ลองเปิด A3 ซ้ำ (ควรถูกบล็อค) ===
    print("\n2️⃣  Try to open A3 again (should be BLOCKED)")
    can_open = tracker.can_open_new('A3')
    print(f"   Can open A3? {can_open}")

    if not can_open:
        print("   ✓ Correctly BLOCKED (position A3 already open)")
    else:
        print("   ✗ ERROR: Should be blocked!")

    # === Test 3: เปิด position A4 (ควรได้) ===
    print("\n3️⃣  Open position A4 BUY @ 4715 (different condition)")
    signal_a4 = {
        'action': 'BUY',
        'condition': 'A4',
        'entry': 4715.0,
        'sl': 4705.0,
        'tp1': 4740.0,
        'tp2': 4750.0,
        'tp3': 4760.0,
        'lot_size': 0.3,
        'timestamp': datetime.now().isoformat()
    }

    can_open = tracker.can_open_new('A4')
    print(f"   Can open A4? {can_open}")

    if can_open:
        pos = tracker.add_position(signal_a4)
        print(f"   ✓ Position opened: {pos.id}")
    else:
        print("   ✗ Cannot open")

    summary = tracker.get_summary()
    print(f"   Open positions: {summary['open_positions']}")
    print(f"   Open conditions: {summary['open_conditions']}")

    # === Test 4: ลองเปิด A5 (ควรถูกบล็อค - max 2 positions) ===
    print("\n4️⃣  Try to open A5 (should be BLOCKED - max positions)")
    can_open = tracker.can_open_new('A5')
    print(f"   Can open A5? {can_open}")

    if not can_open:
        print("   ✓ Correctly BLOCKED (max 2 positions)")
    else:
        print("   ✗ ERROR: Should be blocked!")

    # === Test 5: ราคาขึ้น → hit TP1 ของ A3 ===
    print("\n5️⃣  Price moves to 4750 → hit A3 TP1")
    tracker.update_positions(
        current_price=4750.0,
        current_high=4755.0,
        current_low=4745.0
    )

    summary = tracker.get_summary()
    print(f"   Open positions: {summary['open_positions']}")
    print(f"   Closed positions: {summary['closed_positions']}")
    print(f"   Total P&L: ${summary['total_pnl']:,.2f}")

    # === Test 6: หลัง A3 ปิด → เปิด A3 ใหม่ได้ ===
    print("\n6️⃣  After A3 closed, try to open A3 again")
    can_open = tracker.can_open_new('A3')
    print(f"   Can open A3? {can_open}")

    if can_open:
        print("   ✓ Can open A3 now (previous position closed)")
        pos = tracker.add_position(signal_a3)
        print(f"   ✓ New position opened: {pos.id}")
    else:
        print("   ✗ ERROR: Should be able to open!")

    summary = tracker.get_summary()
    print(f"   Open positions: {summary['open_positions']}")

    # === Test 7: ราคาลง → hit SL ของ A4 ===
    print("\n7️⃣  Price drops to 4705 → hit A4 SL")
    tracker.update_positions(
        current_price=4705.0,
        current_high=4710.0,
        current_low=4700.0
    )

    summary = tracker.get_summary()
    print(f"   Open positions: {summary['open_positions']}")
    print(f"   Closed positions: {summary['closed_positions']}")
    print(f"   Total P&L: ${summary['total_pnl']:,.2f}")
    print(f"   Win Rate: {summary['win_rate']:.1f}%")

    print("\n" + "="*70)
    print("✅ All tests completed!")
    print("="*70)


if __name__ == "__main__":
    test_position_tracking()
