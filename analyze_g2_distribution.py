"""
Analyze Condition Distribution of G2 Passed Signals

รายงาน distribution ของ Conditions (A1-A6) ที่ผ่าน G2
"""

from utils import create_connector
from agents.g1_signal_logic import G1MarketScanner
from agents.g2_quant_analysis import G2QuantAnalyzer
from collections import Counter

def main():
    print("\n" + "="*70)
    print("CONDITION DISTRIBUTION ANALYSIS")
    print("="*70)
    print("\nAnalyzing all G2-passed signals...\n")

    # Initialize agents
    g1_scanner = G1MarketScanner(config={'verbose': False})
    g2_analyzer = G2QuantAnalyzer(config={'verbose': False})

    # Get data
    print("📊 Fetching market data...")
    with create_connector('simulate') as conn:
        market_data = conn.get_latest_candles('XAUUSD', m5_count=600, h1_count=100)

    m5_candles = market_data['m5_ohlcv']
    h1_candles = market_data['h1_candles']

    print(f"✓ Retrieved {len(m5_candles)} M5 candles")
    print(f"✓ Retrieved {len(h1_candles)} H1 candles\n")

    # Scan candles
    min_m5 = 100
    g1_count = 0
    g2_count = 0

    conditions = []
    patterns = []
    rsi_zones = []
    h1_trends = []

    print("🔍 Scanning candles...\n")

    for i in range(min_m5, len(m5_candles) - 50):
        # Get window
        m5_window = m5_candles[i-min_m5:i]
        h1_window = h1_candles[-50:]

        current_data = {
            'm5_ohlcv': m5_window,
            'h1_candles': h1_window,
            'current_price': m5_window[-1]['close'],
            'timestamp': str(m5_window[-1]['time']),
            'symbol': 'XAUUSD'
        }

        # G1
        world_state = g1_scanner.scan_conditions(current_data)
        if not world_state:
            continue

        g1_count += 1

        # G2
        confidence_data = g2_analyzer.analyze(world_state)
        if not confidence_data:
            continue

        g2_count += 1

        # Collect stats
        conditions.append(world_state['condition_candidate'])
        patterns.append(world_state.get('pattern_candidate', 'ไม่มี'))
        rsi_zones.append(world_state['rsi_zone'])
        h1_trends.append(world_state['h1_trend'])

    # Print results
    print(f"{'='*70}\n")
    print(f"📊 RESULTS\n")
    print(f"{'='*70}\n")
    print(f"Total candles scanned: {len(m5_candles) - min_m5 - 50}")
    print(f"G1 candidates: {g1_count}")
    print(f"G2 passed: {g2_count}\n")

    print(f"{'='*70}")
    print(f"CONDITION DISTRIBUTION (G2 Passed)")
    print(f"{'='*70}\n")

    condition_counts = Counter(conditions)
    total = len(conditions)

    # Sort by A1-A6 order
    condition_order = ['A1_uptrend', 'A2_downtrend', 'A3_mountain',
                       'A4_sideways_up', 'A5_sideways_down', 'A6_unclear']

    for cond in condition_order:
        count = condition_counts.get(cond, 0)
        pct = (count / total * 100) if total > 0 else 0
        bar = '█' * int(pct / 2)  # Visual bar
        print(f"{cond:20s}: {count:4d} ({pct:5.1f}%) {bar}")

    # Other stats
    print(f"\n{'='*70}")
    print(f"PATTERN DISTRIBUTION")
    print(f"{'='*70}\n")

    pattern_counts = Counter(patterns)
    for pattern, count in pattern_counts.most_common():
        pct = (count / total * 100) if total > 0 else 0
        print(f"{pattern:20s}: {count:4d} ({pct:5.1f}%)")

    print(f"\n{'='*70}")
    print(f"RSI ZONE DISTRIBUTION")
    print(f"{'='*70}\n")

    rsi_counts = Counter(rsi_zones)
    for zone, count in rsi_counts.most_common():
        pct = (count / total * 100) if total > 0 else 0
        print(f"{zone:20s}: {count:4d} ({pct:5.1f}%)")

    print(f"\n{'='*70}")
    print(f"H1 TREND DISTRIBUTION")
    print(f"{'='*70}\n")

    trend_counts = Counter(h1_trends)
    for trend, count in trend_counts.most_common():
        pct = (count / total * 100) if total > 0 else 0
        print(f"{trend:20s}: {count:4d} ({pct:5.1f}%)")

    print(f"\n{'='*70}\n")


if __name__ == "__main__":
    main()
