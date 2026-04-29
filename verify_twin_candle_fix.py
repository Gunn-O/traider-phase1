"""
Verify Twin Candle Detection Fix
ตรวจสอบว่า is_twin_candle() หลังแก้แล้ว detect คู่ที่ควรเจอได้หรือไม่
"""

import os
import sys
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.data_connector import create_connector
from utils.pattern_utils import is_twin_candle, calc_candle_body
from config import MIN_TWIN_CANDLE_BODY, MAX_TWIN_CANDLE_GAP

load_dotenv()

def main():
    print("="*70)
    print("TWIN CANDLE DETECTION FIX VERIFICATION")
    print("="*70)

    # Create connector and get M5 data
    connector = create_connector('simulate')
    connector.connect()

    print("\n[1] Fetching M5 data...")
    candles = connector.get_latest_candles('XAUUSD', 'M5', 55)

    if not candles or len(candles) < 2:
        print("❌ No candles fetched")
        return

    print(f"✓ Got {len(candles)} candles")

    # Calculate range
    prices = [c['close'] for c in candles]
    range_usd = max(prices) - min(prices)
    range_pip = int(range_usd * 100)

    print(f"\n[2] Range Analysis:")
    print(f"   Range: ${range_usd:.2f} ({range_pip} pip)")
    print(f"   Min twin body threshold: {MIN_TWIN_CANDLE_BODY*100:.1f}% = {range_usd * MIN_TWIN_CANDLE_BODY:.2f} USD = {int(range_usd * MIN_TWIN_CANDLE_BODY * 100)} pip")
    print(f"   Max gap threshold: {MAX_TWIN_CANDLE_GAP} pip")

    # Check all consecutive pairs
    print(f"\n[3] Checking all consecutive candle pairs:")
    print("-"*70)

    twin_pairs = []
    for i in range(len(candles) - 1):
        c1 = candles[i]
        c2 = candles[i+1]

        body1 = calc_candle_body(c1)
        body2 = calc_candle_body(c2)
        gap = abs(c1['close'] - c2['open']) * 100  # pip

        # Check thresholds manually
        body1_ok = body1 >= range_usd * MIN_TWIN_CANDLE_BODY
        body2_ok = body2 >= range_usd * MIN_TWIN_CANDLE_BODY
        gap_ok = gap <= MAX_TWIN_CANDLE_GAP

        # Call is_twin_candle()
        is_twin = is_twin_candle(c1, c2, range_usd)

        # Print pairs that meet body requirement
        if body1_ok and body2_ok:
            status = "✓ TWIN" if is_twin else "✗ NOT TWIN"
            print(f"[{i:2d}-{i+1:2d}] {status}")
            print(f"   Body1: {body1:.2f} USD ({int(body1*100)} pip) {'✓' if body1_ok else '✗'}")
            print(f"   Body2: {body2:.2f} USD ({int(body2*100)} pip) {'✓' if body2_ok else '✗'}")
            print(f"   Gap: {gap:.1f} pip {'✓' if gap_ok else '✗'}")
            print(f"   c1.close: {c1['close']:.2f}, c2.open: {c2['open']:.2f}")

            if is_twin:
                twin_pairs.append((i, i+1))

            print()

    # Summary
    print("="*70)
    print(f"RESULT: Found {len(twin_pairs)} twin candle pairs")
    if twin_pairs:
        print(f"Pairs: {twin_pairs}")
        print("✅ Twin candle detection is working!")
    else:
        print("⚠️ No twin candles detected")
        print("   Check if:")
        print("   1. Candles have large enough bodies (≥2.5% Range)")
        print("   2. Gap between c1.close and c2.open ≤ 50 pip")
    print("="*70)

if __name__ == "__main__":
    main()
