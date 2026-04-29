"""
Extract Ground Truth from Backtest Results

ใช้ trades ที่ผ่าน G1→G2→G3 จาก backtest จริง
บันทึก candle data + expected output เป็น ground truth
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import create_connector
from agents.g1_signal_logic import G1MarketScanner
from agents.g2_quant_analysis import G2QuantAnalyzer
from agents.g3_decision_mock import G3MockDecisionAgent


def extract_ground_truth_cases(num_cases=10):
    """
    Extract ground truth cases from real market data

    Returns:
        list of ground truth cases with real candle data
    """
    print("\n" + "="*70)
    print("EXTRACTING GROUND TRUTH FROM REAL DATA")
    print("="*70)
    print(f"\nTarget: {num_cases} diverse cases")
    print("Strategy: Scan real data, label manually by pipeline output\n")

    # Initialize agents
    g1 = G1MarketScanner(config={'verbose': False})
    g2 = G2QuantAnalyzer(config={'verbose': False})
    g3 = G3MockDecisionAgent(config={'verbose': False})

    # Get real data
    print("📊 Fetching real market data...")
    with create_connector('simulate') as conn:
        market_data = conn.get_latest_candles('XAUUSD', m5_count=600, h1_count=100)

    m5_candles = market_data['m5_ohlcv']
    h1_candles = market_data['h1_candles']

    print(f"✓ Retrieved {len(m5_candles)} M5 candles")
    print(f"✓ Retrieved {len(h1_candles)} H1 candles\n")

    # Collect diverse cases
    cases = []
    condition_counts = {}
    action_counts = {'BUY': 0, 'SELL': 0}

    min_m5 = 100

    print("🔍 Scanning for diverse cases...\n")

    for i in range(min_m5, len(m5_candles) - 50):
        if len(cases) >= num_cases:
            break

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
        world_state = g1.scan_conditions(current_data)
        if not world_state:
            continue

        # G2
        confidence_data = g2.analyze(world_state)
        if not confidence_data:
            continue

        # G3
        decision = g3.decide(world_state, confidence_data)
        if not decision:
            continue

        # Check diversity
        condition = world_state['condition_candidate']
        action = decision['action']

        # Limit per condition (max 3 of each)
        if condition_counts.get(condition, 0) >= 3:
            continue

        # Balance BUY/SELL (max 6 of each)
        if action_counts.get(action, 0) >= 6:
            continue

        # Store case
        case_id = f"GT{len(cases)+1:03d}"

        # Simplify candle data (keep only essential fields)
        m5_simple = [
            {
                'time': str(c['time']),
                'open': float(c['open']),
                'high': float(c['high']),
                'low': float(c['low']),
                'close': float(c['close'])
            }
            for c in m5_window
        ]

        h1_simple = [
            {
                'time': str(c['time']),
                'open': float(c['open']),
                'high': float(c['high']),
                'low': float(c['low']),
                'close': float(c['close'])
            }
            for c in h1_window
        ]

        case = {
            'id': case_id,
            'description': f"{condition}, {world_state.get('pattern_candidate', 'ไม่มี')}, RSI {world_state['rsi']:.1f} → {action}",
            'm5_ohlcv': m5_simple,
            'h1_candles': h1_simple,
            'expected_condition': condition,
            'expected_pattern': world_state.get('pattern_candidate', 'ไม่มี'),
            'expected_action': action,
            'expected_rsi_range': (world_state['rsi'] - 5, world_state['rsi'] + 5),
            'metadata': {
                'timestamp': str(world_state['timestamp']),
                'confidence': confidence_data['confidence'],
                'h1_trend': world_state['h1_trend'],
                'session': world_state['session'],
                'entry': decision['entry'],
                'sl': decision['sl'],
                'tp1': decision['tp1']
            }
        }

        cases.append(case)
        condition_counts[condition] = condition_counts.get(condition, 0) + 1
        action_counts[action] = action_counts.get(action, 0) + 1

        print(f"   ✓ {case_id}: {condition} + {world_state.get('pattern_candidate', 'ไม่มี')} → {action} (RSI {world_state['rsi']:.1f})")

    print(f"\n{'='*70}")
    print(f"📊 Extracted {len(cases)} ground truth cases")
    print(f"\nDistribution:")
    print(f"   By Condition:")
    for cond, count in sorted(condition_counts.items()):
        print(f"      {cond}: {count}")
    print(f"   By Action:")
    for act, count in sorted(action_counts.items()):
        print(f"      {act}: {count}")
    print(f"{'='*70}\n")

    return cases


def save_ground_truth(cases, filename='tests/ground_truth_real.json'):
    """Save ground truth cases to JSON file"""
    os.makedirs('tests', exist_ok=True)

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(cases, f, indent=2, ensure_ascii=False)

    print(f"✓ Saved to {filename}")


def main():
    """Main entry point"""
    cases = extract_ground_truth_cases(num_cases=10)

    if len(cases) >= 8:  # At least 8 cases (80% of target)
        save_ground_truth(cases)
        print(f"\n✅ Successfully extracted {len(cases)} ground truth cases!")
        print(f"   These cases represent real market conditions that passed G1→G2→G3")
        print(f"   Use them to validate pipeline accuracy\n")
    else:
        print(f"\n⚠️  Only found {len(cases)} cases (target: 10)")
        print(f"   Consider adjusting diversity constraints or scanning more data\n")


if __name__ == "__main__":
    main()
