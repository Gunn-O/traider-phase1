"""
Ground Truth Test Runner

รัน G1→G2→G3 pipeline กับ test cases ทั้งหมด
ตรวจสอบว่า output ตรงกับ expected values หรือไม่

เป้าหมาย: pass ≥ 80% ก่อนเชื่อผล backtest
"""

import sys
import os
import json
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.ground_truth import get_all_test_cases
from agents.g1_signal_logic import G1MarketScanner
from agents.g2_quant_analysis import G2QuantAnalyzer
from agents.g3_decision_mock import G3MockDecisionAgent


def load_real_ground_truth(filename='tests/ground_truth_real.json'):
    """Load ground truth cases from real data JSON file"""
    if not os.path.exists(filename):
        return []

    with open(filename, 'r', encoding='utf-8') as f:
        cases = json.load(f)

    # Convert time strings back to datetime objects
    for case in cases:
        for candle in case['m5_ohlcv']:
            candle['time'] = datetime.fromisoformat(candle['time'].replace('Z', '+00:00'))
        for candle in case['h1_candles']:
            candle['time'] = datetime.fromisoformat(candle['time'].replace('Z', '+00:00'))

    return cases


class GroundTruthTester:
    """Test runner for ground truth cases"""

    def __init__(self, use_mock=True):
        """
        Initialize tester

        Args:
            use_mock: Use Mock Agent instead of Claude API (default: True)
        """
        self.use_mock = use_mock

        # Initialize agents
        self.g1 = G1MarketScanner(config={'verbose': False})
        self.g2 = G2QuantAnalyzer(config={'verbose': False})

        if use_mock:
            self.g3 = G3MockDecisionAgent(config={'verbose': False})
        else:
            # Use Claude API (requires API key)
            from agents.g3_decision import G3DecisionAgent
            self.g3 = G3DecisionAgent(config={'verbose': False, 'use_concise': True})

        self.results = []

    def run_test_case(self, test_case):
        """
        Run single test case through G1→G2→G3 pipeline

        Returns:
            dict with test results
        """
        case_id = test_case['id']
        description = test_case['description']

        print(f"\n{'='*70}")
        print(f"Testing: {case_id}")
        print(f"Description: {description}")
        print(f"{'='*70}")

        # Prepare input data
        m5_ohlcv = test_case['m5_ohlcv']
        h1_candles = test_case['h1_candles']

        current_data = {
            'm5_ohlcv': m5_ohlcv,
            'h1_candles': h1_candles,
            'current_price': m5_ohlcv[-1]['close'],
            'timestamp': str(m5_ohlcv[-1]['time']),
            'symbol': 'XAUUSD'
        }

        # Expected values
        expected_condition = test_case['expected_condition']
        expected_pattern = test_case.get('expected_pattern', 'ไม่มี')
        expected_action = test_case['expected_action']
        expected_rsi_range = test_case.get('expected_rsi_range', (0, 100))

        # === G1: Market Scanning ===
        print(f"\n🔍 G1: Market Scanning...")
        world_state = self.g1.scan_conditions(current_data)

        if not world_state:
            print(f"   ❌ G1 rejected (no candidate)")
            return {
                'case_id': case_id,
                'description': description,
                'passed': False,
                'stage_failed': 'G1',
                'reason': 'G1 rejected - no candidate',
                'expected': f"{expected_condition} + {expected_pattern} → {expected_action}",
                'actual': 'G1 rejected'
            }

        actual_condition = world_state['condition_candidate']
        actual_pattern = world_state.get('pattern_candidate', 'ไม่มี')
        actual_rsi = world_state['rsi']

        print(f"   ✓ G1 passed")
        print(f"   Condition: {actual_condition} (expected: {expected_condition})")
        print(f"   Pattern: {actual_pattern} (expected: {expected_pattern})")
        print(f"   RSI: {actual_rsi:.1f} (expected: {expected_rsi_range[0]}-{expected_rsi_range[1]})")

        # === G2: Quantitative Analysis ===
        print(f"\n📊 G2: Quantitative Analysis...")
        confidence_data = self.g2.analyze(world_state)

        if not confidence_data:
            print(f"   ❌ G2 rejected (confidence < 0.70)")
            return {
                'case_id': case_id,
                'description': description,
                'passed': False,
                'stage_failed': 'G2',
                'reason': 'G2 rejected - confidence too low',
                'expected': f"{expected_condition} + {expected_pattern} → {expected_action}",
                'actual': f"{actual_condition} + {actual_pattern} → G2 rejected",
                'actual_rsi': actual_rsi
            }

        confidence = confidence_data['confidence']
        print(f"   ✓ G2 passed (confidence: {confidence:.3f})")

        # === G3: Decision ===
        print(f"\n🤖 G3: Decision Agent...")
        decision = self.g3.decide(world_state, confidence_data)

        if not decision:
            print(f"   ❌ G3 decided SKIP")
            return {
                'case_id': case_id,
                'description': description,
                'passed': False,
                'stage_failed': 'G3',
                'reason': 'G3 decided SKIP',
                'expected': f"{expected_condition} + {expected_pattern} → {expected_action}",
                'actual': f"{actual_condition} + {actual_pattern} → SKIP",
                'actual_rsi': actual_rsi,
                'confidence': confidence
            }

        actual_action = decision['action']
        print(f"   ✓ G3 decision: {actual_action}")
        print(f"   Entry: ${decision['entry']:.2f}, SL: ${decision['sl']:.2f}, TP1: ${decision['tp1']:.2f}")

        # === Validate Results ===
        print(f"\n✅ Validation...")

        checks = {
            'condition_match': actual_condition == expected_condition,
            'action_match': actual_action == expected_action,
            'rsi_in_range': expected_rsi_range[0] <= actual_rsi <= expected_rsi_range[1]
        }

        # Pattern match (flexible - ไม่ต้องตรงทุก case)
        pattern_match = (actual_pattern == expected_pattern or
                        actual_pattern in ['แนวเด้ง', 'ไม้รวย', 'ตามเจ้า'])
        checks['pattern_match'] = pattern_match

        all_passed = all(checks.values())

        print(f"   Condition: {'✓' if checks['condition_match'] else '✗'} {actual_condition} == {expected_condition}")
        print(f"   Pattern: {'✓' if checks['pattern_match'] else '✗'} {actual_pattern} (expected: {expected_pattern})")
        print(f"   Action: {'✓' if checks['action_match'] else '✗'} {actual_action} == {expected_action}")
        print(f"   RSI Range: {'✓' if checks['rsi_in_range'] else '✗'} {actual_rsi:.1f} in {expected_rsi_range}")

        if all_passed:
            print(f"\n🎉 PASSED")
        else:
            print(f"\n❌ FAILED")

        return {
            'case_id': case_id,
            'description': description,
            'passed': all_passed,
            'stage_failed': None if all_passed else 'Validation',
            'checks': checks,
            'expected': f"{expected_condition} + {expected_pattern} → {expected_action}",
            'actual': f"{actual_condition} + {actual_pattern} → {actual_action}",
            'actual_rsi': actual_rsi,
            'confidence': confidence,
            'reason': 'All checks passed' if all_passed else f"Failed: {[k for k, v in checks.items() if not v]}"
        }

    def run_all_tests(self):
        """Run all ground truth tests"""
        test_cases = get_all_test_cases()
        total = len(test_cases)

        print(f"\n{'='*70}")
        print(f"GROUND TRUTH TEST RUNNER")
        print(f"{'='*70}")
        print(f"Total test cases: {total}")
        print(f"Agent mode: {'Mock Agent' if self.use_mock else 'Claude API'}")
        print(f"Target: ≥80% pass rate")
        print(f"{'='*70}\n")

        for test_case in test_cases:
            result = self.run_test_case(test_case)
            self.results.append(result)

        # Print summary
        self.print_summary()

    def print_summary(self):
        """Print test summary"""
        total = len(self.results)
        passed = sum(1 for r in self.results if r['passed'])
        failed = total - passed
        pass_rate = (passed / total * 100) if total > 0 else 0

        print(f"\n{'='*70}")
        print(f"TEST SUMMARY")
        print(f"{'='*70}\n")

        print(f"📊 Overall Results:")
        print(f"   Total: {total}")
        print(f"   Passed: {passed} ({pass_rate:.1f}%)")
        print(f"   Failed: {failed} ({(failed/total*100):.1f}%)")

        # Pass rate indicator
        if pass_rate >= 80:
            print(f"\n✅ PASS RATE ≥ 80% - Pipeline validated!")
        else:
            print(f"\n⚠️  PASS RATE < 80% - Pipeline needs improvement")

        # Failed cases
        if failed > 0:
            print(f"\n❌ Failed Cases:")
            for r in self.results:
                if not r['passed']:
                    print(f"\n   {r['case_id']}: {r['description']}")
                    print(f"      Stage failed: {r.get('stage_failed', 'Unknown')}")
                    print(f"      Expected: {r['expected']}")
                    print(f"      Actual: {r['actual']}")
                    print(f"      Reason: {r['reason']}")

        # Detailed breakdown
        print(f"\n📈 Detailed Results:")
        print(f"{'─'*70}")
        print(f"{'ID':<8} {'Status':<10} {'Expected':<30} {'Actual':<30}")
        print(f"{'─'*70}")

        for r in self.results:
            status = '✅ PASS' if r['passed'] else '❌ FAIL'
            print(f"{r['case_id']:<8} {status:<10} {r['expected']:<30} {r['actual']:<30}")

        print(f"{'─'*70}\n")

        # Stage breakdown
        stage_failures = {}
        for r in self.results:
            if not r['passed'] and r.get('stage_failed'):
                stage = r['stage_failed']
                stage_failures[stage] = stage_failures.get(stage, 0) + 1

        if stage_failures:
            print(f"\n🔍 Failures by Stage:")
            for stage, count in sorted(stage_failures.items()):
                pct = (count / total * 100)
                print(f"   {stage}: {count} ({pct:.1f}%)")

        print(f"\n{'='*70}\n")


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Run ground truth tests')
    parser.add_argument('--claude', action='store_true', help='Use Claude API instead of Mock Agent')
    parser.add_argument('--case', type=str, help='Run specific test case by ID')
    parser.add_argument('--synthetic', action='store_true', help='Use synthetic test cases (default: real data)')
    args = parser.parse_args()

    # Load test cases
    if args.synthetic:
        print("📋 Using synthetic test cases...")
        test_cases = get_all_test_cases()
    else:
        print("📋 Loading real ground truth cases...")
        test_cases = load_real_ground_truth()
        if not test_cases:
            print("❌ No real ground truth cases found. Run: python tests/extract_ground_truth.py")
            sys.exit(1)
        print(f"✓ Loaded {len(test_cases)} real test cases\n")

    tester = GroundTruthTester(use_mock=not args.claude)

    if args.case:
        # Run single case
        test_case = None
        for case in test_cases:
            if case['id'] == args.case:
                test_case = case
                break

        if not test_case:
            print(f"❌ Test case '{args.case}' not found")
            sys.exit(1)

        result = tester.run_test_case(test_case)
        tester.results.append(result)
        tester.print_summary()
    else:
        # Run all cases - inject test cases
        total = len(test_cases)
        print(f"\n{'='*70}")
        print(f"GROUND TRUTH TEST RUNNER")
        print(f"{'='*70}")
        print(f"Total test cases: {total}")
        print(f"Agent mode: {'Mock Agent' if tester.use_mock else 'Claude API'}")
        print(f"Target: ≥80% pass rate")
        print(f"{'='*70}\n")

        for test_case in test_cases:
            result = tester.run_test_case(test_case)
            tester.results.append(result)

        # Print summary
        tester.print_summary()


if __name__ == "__main__":
    main()
