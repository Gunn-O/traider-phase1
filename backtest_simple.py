"""
Simple Backtest Script - Phase I Proof of Concept

ทดสอบ G1 + G2 agents กับข้อมูลย้อนหลัง
แสดงสถิติว่าเจอ signals กี่ครั้ง และ pattern distribution

Note: นี่คือ POC - ยังไม่ใช่ full backtest ที่มี G3 Decision + Simulated Execution
"""

import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict
import json

from utils import create_connector
from agents.g1_signal_logic import G1MarketScanner
from agents.g2_quant_analysis import G2QuantAnalyzer


class SimpleBacktest:
    """Simple backtest runner for Phase I POC"""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.g1_scanner = G1MarketScanner(config={'verbose': False})
        self.g2_analyzer = G2QuantAnalyzer(config={'verbose': False})

        self.results = {
            'total_candles_scanned': 0,
            'g1_candidates': 0,
            'g2_passed': 0,
            'signals': [],
            'condition_distribution': {},
            'pattern_distribution': {},
            'rsi_zones': {},
            'sessions': {}
        }

    def run(self, start_date: datetime, end_date: datetime, symbol: str = 'XAUUSD'):
        """
        Run backtest over date range

        Args:
            start_date: Start date (within last 60 days for yfinance)
            end_date: End date
            symbol: Trading symbol

        Returns:
            results Dict with statistics
        """
        print(f"\n{'='*70}")
        print(f"SIMPLE BACKTEST - G1 + G2 AGENTS")
        print(f"{'='*70}")
        print(f"Symbol: {symbol}")
        print(f"Period: {start_date.date()} to {end_date.date()}")
        print(f"Mode: Simulate (yfinance data)")
        print(f"{'='*70}\n")

        # Get data using simulate mode
        print(f"📊 Fetching market data...")
        with create_connector('simulate') as conn:
            # For simulate mode, we get last 60 days
            # We'll process it candle by candle to simulate real-time
            market_data = conn.get_latest_candles(symbol, m5_count=500, h1_count=100)

        print(f"✓ Retrieved {len(market_data['m5_ohlcv'])} M5 candles")
        print(f"✓ Retrieved {len(market_data['h1_candles'])} H1 candles")

        # Process candles in sliding window
        m5_candles = market_data['m5_ohlcv']
        h1_candles = market_data['h1_candles']

        # Minimum candles needed
        min_m5 = 100
        min_h1 = 50

        if len(m5_candles) < min_m5 or len(h1_candles) < min_h1:
            print(f"❌ Not enough data for backtest")
            return self.results

        # Slide through candles
        print(f"\n🔍 Scanning candles (sliding window)...")
        print(f"   M5 window: {min_m5} candles")
        print(f"   H1 window: {min_h1} candles")

        scan_count = 0
        for i in range(min_m5, len(m5_candles)):
            # Get window of data
            m5_window = m5_candles[i-min_m5:i]

            # For H1, just use the last min_h1 candles (simpler approach)
            if len(h1_candles) >= min_h1:
                h1_window = h1_candles[-min_h1:]
            else:
                continue

            # Create market_data dict for this window
            current_data = {
                'm5_ohlcv': m5_window,
                'h1_candles': h1_window,
                'current_price': m5_window[-1]['close'],
                'timestamp': str(m5_window[-1]['time']),
                'symbol': symbol
            }

            # Run G1
            world_state = self.g1_scanner.scan_conditions(current_data)

            self.results['total_candles_scanned'] += 1
            scan_count += 1

            if world_state:
                # G1 found candidate
                self.results['g1_candidates'] += 1

                # Run G2
                confidence_data = self.g2_analyzer.analyze(world_state)

                if confidence_data:
                    # G2 passed - this is a signal
                    self.results['g2_passed'] += 1

                    # Record signal
                    signal = {
                        'timestamp': world_state['timestamp'],
                        'price': world_state['price'],
                        'condition': world_state['condition_candidate'],
                        'pattern': world_state['pattern_candidate'],
                        'rsi': world_state['rsi'],
                        'rsi_zone': world_state['rsi_zone'],
                        'confidence': confidence_data['confidence'],
                        'h1_trend': world_state['h1_trend'],
                        'session': world_state['session']
                    }

                    self.results['signals'].append(signal)

                    # Update distributions
                    cond = world_state['condition_candidate']
                    self.results['condition_distribution'][cond] = \
                        self.results['condition_distribution'].get(cond, 0) + 1

                    pattern = world_state['pattern_candidate']
                    self.results['pattern_distribution'][pattern] = \
                        self.results['pattern_distribution'].get(pattern, 0) + 1

                    rsi_zone = world_state['rsi_zone']
                    self.results['rsi_zones'][rsi_zone] = \
                        self.results['rsi_zones'].get(rsi_zone, 0) + 1

                    session = world_state['session']
                    self.results['sessions'][session] = \
                        self.results['sessions'].get(session, 0) + 1

                    if self.verbose:
                        print(f"\n✓ Signal #{self.results['g2_passed']}: "
                              f"{cond} + {pattern} @ ${world_state['price']:.2f} "
                              f"(confidence: {confidence_data['confidence']:.3f})")

            # Progress update every 50 candles
            if scan_count % 50 == 0:
                print(f"   Scanned: {scan_count}/{len(m5_candles)-min_m5} "
                      f"| Candidates: {self.results['g1_candidates']} "
                      f"| Signals: {self.results['g2_passed']}")

        return self.results

    def print_summary(self):
        """Print backtest summary statistics"""
        print(f"\n{'='*70}")
        print(f"BACKTEST SUMMARY")
        print(f"{'='*70}\n")

        total = self.results['total_candles_scanned']
        g1_cand = self.results['g1_candidates']
        signals = self.results['g2_passed']

        print(f"📊 Overall Statistics:")
        print(f"   Total candles scanned: {total}")

        if total > 0:
            print(f"   G1 candidates found:   {g1_cand} ({g1_cand/total*100:.2f}%)")
            print(f"   G2 signals passed:     {signals} ({signals/total*100:.2f}%)")
        else:
            print(f"   G1 candidates found:   {g1_cand}")
            print(f"   G2 signals passed:     {signals}")

        if signals > 0:
            print(f"\n📈 Signal Distribution:")

            print(f"\n   By Condition (A1-A6):")
            for cond, count in sorted(self.results['condition_distribution'].items(),
                                      key=lambda x: x[1], reverse=True):
                pct = count / signals * 100
                print(f"      {cond:20s}: {count:3d} ({pct:5.1f}%)")

            print(f"\n   By Pattern (B1-B3):")
            for pattern, count in sorted(self.results['pattern_distribution'].items(),
                                         key=lambda x: x[1], reverse=True):
                pct = count / signals * 100
                print(f"      {pattern:20s}: {count:3d} ({pct:5.1f}%)")

            print(f"\n   By RSI Zone:")
            for zone, count in sorted(self.results['rsi_zones'].items(),
                                      key=lambda x: x[1], reverse=True):
                pct = count / signals * 100
                print(f"      {zone:20s}: {count:3d} ({pct:5.1f}%)")

            print(f"\n   By Session:")
            for session, count in sorted(self.results['sessions'].items(),
                                         key=lambda x: x[1], reverse=True):
                pct = count / signals * 100
                print(f"      {session:20s}: {count:3d} ({pct:5.1f}%)")

            # Show last 10 signals
            print(f"\n📝 Last 10 Signals:")
            for i, sig in enumerate(self.results['signals'][-10:], 1):
                print(f"\n   {i}. {sig['timestamp']}")
                print(f"      {sig['condition']} + {sig['pattern']}")
                print(f"      Price: ${sig['price']:.2f} | RSI: {sig['rsi']:.1f} ({sig['rsi_zone']})")
                print(f"      Confidence: {sig['confidence']:.3f} | H1: {sig['h1_trend']} | {sig['session']}")

        else:
            print(f"\n⏭  No signals generated during this period")
            print(f"   Consider:")
            print(f"   - Using longer time period (more data)")
            print(f"   - Adjusting G1/G2 thresholds")
            print(f"   - Market may be in low-volatility period")

        print(f"\n{'='*70}")
        print(f"💡 Note: This is a POC backtest (G1 + G2 only)")
        print(f"   Full backtest with G3 Decision + Simulated Execution coming soon")
        print(f"{'='*70}\n")

    def save_results(self, filename: str = 'backtest_results.json'):
        """Save results to JSON file"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False, default=str)
        print(f"✓ Results saved to {filename}")


def main():
    """Run simple backtest"""
    from dotenv import load_dotenv
    load_dotenv()

    # Use recent dates (within 60 days for yfinance)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)  # Last 30 days

    # Run backtest
    bt = SimpleBacktest(verbose=False)
    results = bt.run(start_date, end_date, symbol='XAUUSD')

    # Print summary
    bt.print_summary()

    # Save results
    # bt.save_results('backtest/results/simple_backtest.json')


if __name__ == "__main__":
    main()
