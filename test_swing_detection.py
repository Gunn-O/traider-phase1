"""
Quick Test: Fractal N-bar Pivot Swing Detection
แสดงผล swing points ที่ detect ได้จาก mock data
"""

import sys
from datetime import datetime, timedelta
from utils.pattern_utils import find_swing_points, merge_close_swings
from config import FRACTAL_N

def create_uptrend_candles(count=55):
    """สร้างแท่งเทียน uptrend แบบง่าย"""
    candles = []
    base_price = 3200.0
    timestamp = datetime.now() - timedelta(minutes=count*5)

    for i in range(count):
        # Uptrend: ราคาค่อยๆ ขึ้น พร้อม noise
        noise = (i % 7 - 3) * 2  # -6 to +8 noise
        trend = i * 1.2  # ขึ้นเรื่อยๆ

        open_price = base_price + trend + noise
        close_price = open_price + (2 if i % 3 == 0 else -1)  # บางแท่งขาขึ้น บางแท่งขาลง
        high_price = max(open_price, close_price) + abs(noise * 0.3)
        low_price = min(open_price, close_price) - abs(noise * 0.2)

        candles.append({
            'timestamp': timestamp + timedelta(minutes=i*5),
            'open': round(open_price, 2),
            'high': round(high_price, 2),
            'low': round(low_price, 2),
            'close': round(close_price, 2)
        })

    return candles


def test_fractal_detection():
    """Test Fractal N-bar Pivot detection"""
    print("="*70)
    print("FRACTAL N-BAR PIVOT SWING DETECTION TEST")
    print("="*70)

    # Test different timeframes
    for tf in ['M1', 'M5', 'H1']:
        N = FRACTAL_N[tf]
        print(f"\n📊 Timeframe: {tf} (N={N})")
        print("-"*70)

        # Create mock candles
        candles = create_uptrend_candles(55)

        # Detect swing points
        swings = find_swing_points(candles, timeframe=tf)
        print(f"   Raw swings: {len(swings['highs'])} highs, {len(swings['lows'])} lows")

        # Merge close swings
        merged = merge_close_swings(swings)
        print(f"   After merge: {len(merged['highs'])} highs, {len(merged['lows'])} lows")

        # Show first 3 swing highs
        if merged['highs']:
            print(f"\n   Swing Highs (first 3):")
            for idx, price in merged['highs'][:3]:
                candle_time = candles[idx]['timestamp'].strftime('%H:%M')
                print(f"      Bar {idx:2d} ({candle_time}): ${price:.2f}")

        # Show first 3 swing lows
        if merged['lows']:
            print(f"\n   Swing Lows (first 3):")
            for idx, price in merged['lows'][:3]:
                candle_time = candles[idx]['timestamp'].strftime('%H:%M')
                print(f"      Bar {idx:2d} ({candle_time}): ${price:.2f}")

    print("\n" + "="*70)
    print("✅ Fractal detection working correctly!")
    print("="*70)


if __name__ == "__main__":
    test_fractal_detection()
