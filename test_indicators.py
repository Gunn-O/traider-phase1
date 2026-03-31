"""
Test Technical Indicators
Run: python test_indicators.py
"""

import pandas as pd
from utils import (
    create_connector,
    calculate_rsi,
    detect_sr_levels,
    detect_trend,
    get_rsi_zone,
    find_nearest_sr_level,
    analyze_candle_pattern,
    calculate_atr
)
from dotenv import load_dotenv

load_dotenv()


def print_section(title: str):
    """Print formatted section header"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print('='*70)


def test_rsi_indicator():
    """Test RSI calculation and zone classification"""
    print_section("1. RSI INDICATOR TEST")

    with create_connector('simulate') as conn:
        data = conn.get_latest_candles('XAUUSD', m5_count=50, h1_count=20)

    df = pd.DataFrame(data['m5_ohlcv'])
    df['rsi'] = calculate_rsi(df, period=14)

    current_rsi = df['rsi'].iloc[-1]
    rsi_zone = get_rsi_zone(current_rsi)

    print(f"\n✓ RSI(14) calculated for {len(df)} candles")
    print(f"✓ Current RSI: {current_rsi:.2f}")
    print(f"✓ Zone: {rsi_zone}")

    # Test different RSI zones
    print(f"\n📊 RSI Zone Classification:")
    test_values = [20, 30, 40, 50, 60, 70, 80]
    for rsi_val in test_values:
        zone = get_rsi_zone(rsi_val)
        print(f"   RSI {rsi_val:2d} → {zone}")

    # Show RSI history
    print(f"\n📈 Last 10 RSI values:")
    for i, (idx, row) in enumerate(df.tail(10).iterrows(), 1):
        rsi_val = row['rsi']
        zone = get_rsi_zone(rsi_val)
        print(f"   {i:2d}. RSI: {rsi_val:5.2f} | Zone: {zone:15s} | Price: {row['close']:7.2f}")

    return True


def test_sr_detection():
    """Test Support/Resistance level detection"""
    print_section("2. SUPPORT/RESISTANCE DETECTION TEST")

    with create_connector('simulate') as conn:
        data = conn.get_latest_candles('XAUUSD', m5_count=100, h1_count=20)

    df = pd.DataFrame(data['m5_ohlcv'])
    current_price = data['current_price']

    # Detect S/R levels with different parameters
    print(f"\n✓ Testing S/R detection with different parameters...")

    # Test 1: Default parameters
    sr_levels = detect_sr_levels(df, swing_window=5, zone_threshold=50, min_touches=2)
    print(f"\n📍 Test 1 (swing_window=5, threshold=50, min_touches=2):")
    print(f"   Found {len(sr_levels)} levels")

    if sr_levels:
        print(f"\n   Top 5 strongest S/R levels:")
        for i, level in enumerate(sr_levels[:5], 1):
            distance = abs(current_price - level['price'])
            print(f"   {i}. ${level['price']:7.2f} | {level['type']:10s} | "
                  f"touches: {level['touches']} | strength: {level['strength']:.2f} | "
                  f"distance: {distance:6.2f}pts")

    # Test 2: Stricter parameters
    sr_levels_strict = detect_sr_levels(df, swing_window=7, zone_threshold=30, min_touches=3)
    print(f"\n📍 Test 2 (swing_window=7, threshold=30, min_touches=3 - stricter):")
    print(f"   Found {len(sr_levels_strict)} levels")

    # Test nearest S/R
    print(f"\n🎯 Nearest S/R Level to current price (${current_price:.2f}):")
    nearest = find_nearest_sr_level(current_price, sr_levels, max_distance=200)
    if nearest:
        print(f"   Price: ${nearest['price']:.2f}")
        print(f"   Type: {nearest['type']}")
        print(f"   Distance: {nearest['distance']:.2f} points")
        print(f"   Touches: {nearest['touches']}")
        print(f"   Strength: {nearest['strength']:.2f}")
    else:
        print(f"   No S/R level within 200 points")

    return True


def test_trend_detection():
    """Test trend detection algorithms"""
    print_section("3. TREND DETECTION TEST")

    with create_connector('simulate') as conn:
        data = conn.get_latest_candles('XAUUSD', m5_count=100, h1_count=50)

    m5_df = pd.DataFrame(data['m5_ohlcv'])
    h1_df = pd.DataFrame(data['h1_candles'])

    print(f"\n✓ Testing trend detection on different timeframes...")

    # M5 trend
    print(f"\n📊 M5 Timeframe (100 candles):")
    m5_ma = detect_trend(m5_df, method='ma_slope')
    m5_hh = detect_trend(m5_df, method='higher_highs')
    m5_combined = detect_trend(m5_df, method='combined')

    print(f"   MA Slope method:    {m5_ma}")
    print(f"   Higher Highs method: {m5_hh}")
    print(f"   Combined:           {m5_combined}")

    # H1 trend
    print(f"\n📊 H1 Timeframe (50 candles):")
    h1_ma = detect_trend(h1_df, method='ma_slope')
    h1_hh = detect_trend(h1_df, method='higher_highs')
    h1_combined = detect_trend(h1_df, method='combined')

    print(f"   MA Slope method:    {h1_ma}")
    print(f"   Higher Highs method: {h1_hh}")
    print(f"   Combined:           {h1_combined}")

    # Alignment check
    print(f"\n🔄 Trend Alignment:")
    if m5_combined == h1_combined:
        print(f"   ✓ M5 and H1 aligned: {h1_combined} → Strong signal")
    else:
        print(f"   ✗ M5 ({m5_combined}) ≠ H1 ({h1_combined}) → Mixed signals")

    return True


def test_candle_patterns():
    """Test candle pattern analysis"""
    print_section("4. CANDLE PATTERN ANALYSIS TEST")

    with create_connector('simulate') as conn:
        data = conn.get_latest_candles('XAUUSD', m5_count=20, h1_count=5)

    candles = data['m5_ohlcv']

    print(f"\n✓ Analyzing last 10 M5 candles...")
    print(f"\n{'#':<3} {'Time':<25} {'Body':<7} {'LWick':<7} {'UWick':<7} {'Pattern'}")
    print('-' * 70)

    for i in range(len(candles) - 10, len(candles)):
        candle = candles[i]
        prev = candles[i-1] if i > 0 else None

        pattern = analyze_candle_pattern(candle, prev)

        # Determine pattern description
        patterns = []
        if pattern['is_engulfing']:
            patterns.append('Engulfing')
        if pattern['has_long_lower_wick']:
            patterns.append('Long Lower Wick')
        if pattern['has_long_upper_wick']:
            patterns.append('Long Upper Wick')
        if pattern['is_doji']:
            patterns.append('Doji')

        direction = '🟢' if pattern['is_bullish'] else '🔴'
        pattern_str = ', '.join(patterns) if patterns else '-'

        print(f"{i+1:<3} {str(candle['time']):<25} "
              f"{pattern['body_size']:>6.2f} "
              f"{pattern['lower_wick']:>6.2f} "
              f"{pattern['upper_wick']:>6.2f} "
              f"{direction} {pattern_str}")

    # Test specific pattern scenarios
    print(f"\n🎯 Pattern Detection Examples:")

    # Find spike reversal candidates (B1 ไม้รวย)
    print(f"\n   Looking for Spike Reversal candidates (B1 ไม้รวย):")
    found_spike = False
    for i in range(len(candles) - 5, len(candles)):
        candle = candles[i]
        pattern = analyze_candle_pattern(candle)

        if pattern['has_long_lower_wick'] and pattern['is_bullish']:
            print(f"   ✓ Found bullish spike at index {i}: "
                  f"Lower wick {pattern['lower_wick']:.2f} > body {pattern['body_size']:.2f}")
            found_spike = True
            break
        elif pattern['has_long_upper_wick'] and pattern['is_bearish']:
            print(f"   ✓ Found bearish spike at index {i}: "
                  f"Upper wick {pattern['upper_wick']:.2f} > body {pattern['body_size']:.2f}")
            found_spike = True
            break

    if not found_spike:
        print(f"   ✗ No obvious spike reversal in last 5 candles")

    return True


def test_atr_calculation():
    """Test ATR calculation"""
    print_section("5. ATR (AVERAGE TRUE RANGE) TEST")

    with create_connector('simulate') as conn:
        data = conn.get_latest_candles('XAUUSD', m5_count=50, h1_count=20)

    m5_df = pd.DataFrame(data['m5_ohlcv'])
    h1_df = pd.DataFrame(data['h1_candles'])

    # Calculate ATR for both timeframes
    m5_df['atr'] = calculate_atr(m5_df, period=14)
    h1_df['atr'] = calculate_atr(h1_df, period=14)

    m5_atr = m5_df['atr'].iloc[-1]
    h1_atr = h1_df['atr'].iloc[-1]

    print(f"\n✓ ATR calculated for M5 and H1 timeframes")
    print(f"\n📊 Current ATR values:")
    print(f"   M5 ATR(14): {m5_atr:6.2f} points")
    print(f"   H1 ATR(14): {h1_atr:6.2f} points")

    print(f"\n💡 ATR Usage:")
    print(f"   - Stop Loss: 1.5-2.0 × ATR = {m5_atr*1.5:.2f} - {m5_atr*2:.2f} points")
    print(f"   - Take Profit: 2.0-3.0 × ATR = {m5_atr*2:.2f} - {m5_atr*3:.2f} points")
    print(f"   - Volatility: {'High' if m5_atr > 20 else 'Normal' if m5_atr > 10 else 'Low'}")

    # ATR history
    print(f"\n📈 Last 5 M5 ATR values:")
    for i, atr_val in enumerate(m5_df['atr'].tail(5).values, 1):
        print(f"   {i}. ATR: {atr_val:6.2f}")

    return True


def main():
    """Run all indicator tests"""
    print("\n" + "="*70)
    print("  TRAIDER PHASE I - TECHNICAL INDICATORS TEST SUITE")
    print("="*70)

    results = []

    try:
        results.append(("RSI Indicator", test_rsi_indicator()))
    except Exception as e:
        print(f"\n❌ RSI Test failed: {e}")
        results.append(("RSI Indicator", False))

    try:
        results.append(("S/R Detection", test_sr_detection()))
    except Exception as e:
        print(f"\n❌ S/R Test failed: {e}")
        results.append(("S/R Detection", False))

    try:
        results.append(("Trend Detection", test_trend_detection()))
    except Exception as e:
        print(f"\n❌ Trend Test failed: {e}")
        results.append(("Trend Detection", False))

    try:
        results.append(("Candle Patterns", test_candle_patterns()))
    except Exception as e:
        print(f"\n❌ Candle Pattern Test failed: {e}")
        results.append(("Candle Patterns", False))

    try:
        results.append(("ATR Calculation", test_atr_calculation()))
    except Exception as e:
        print(f"\n❌ ATR Test failed: {e}")
        results.append(("ATR Calculation", False))

    # Summary
    print_section("TEST SUMMARY")
    all_passed = True
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {status} - {test_name}")
        if not passed:
            all_passed = False

    print("\n" + "="*70)
    if all_passed:
        print("  🎉 ALL TESTS PASSED!")
        print("  Ready for G1 Agent (Market Scanning) development")
    else:
        print("  ⚠️  SOME TESTS FAILED - Please review errors above")
    print("="*70 + "\n")

    return all_passed


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
