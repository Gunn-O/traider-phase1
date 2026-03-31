"""
Full Backtest Script - Phase I Complete Pipeline

Pipeline: G1 → G2 → G3 (Claude API) → G3b → G3c → Simulated Execution

สร้าง trade log พร้อม:
- Win Rate
- Average P&L
- Best/Worst Conditions
- Best RSI Zones
- Session performance

Mode: ใช้ Claude API จริง (claude-sonnet-4-5)
"""

import pandas as pd
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import os

from utils import create_connector
from utils.simulated_execution import calculate_simulated_result, calculate_rr_ratio
from agents.g1_signal_logic import G1MarketScanner
from agents.g2_quant_analysis import G2QuantAnalyzer
from agents.g3_decision import G3DecisionAgent
from agents.g3_decision_mock import G3MockDecisionAgent  # Fallback
from agents.g3_money_management import calculate_lot_size
from agents.g3_risk_gate import guardian_check


class FullBacktest:
    """
    Full Backtest Runner with Complete Pipeline

    G1 → G2 → G3 (Claude) → G3b → G3c → Simulated Execution
    """

    def __init__(self, use_claude_api: bool = False, verbose: bool = False, validate_mode: bool = False, debug_rejections: int = 0):
        """
        Initialize Full Backtest

        Args:
            use_claude_api: Use real Claude API (default: False - uses Mock)
                           ⚠️ Claude API costs money! Use Mock for backtest
            verbose: Print detailed logs
            validate_mode: If True, use Claude API for first 20 signals only (validation)
            debug_rejections: Print first N rejection details (Mock Agent only)
        """
        self.use_claude_api = use_claude_api
        self.verbose = verbose
        self.validate_mode = validate_mode
        self.debug_rejections = debug_rejections
        self.claude_calls_count = 0
        self.max_claude_calls = 20 if validate_mode else 999999

        # Initialize agents
        self.g1_scanner = G1MarketScanner(config={'verbose': False})
        self.g2_analyzer = G2QuantAnalyzer(config={'verbose': False})

        if use_claude_api:
            try:
                self.g3_decision = G3DecisionAgent(
                    config={
                        'verbose': False,
                        'use_concise': True  # Use concise strategy (1.5k chars)
                    }
                )
                mode_text = "Validation (20 signals)" if validate_mode else "Full"
                print(f"✓ Using Claude API (claude-sonnet-4-5) - {mode_text} mode")
                print(f"  Strategy: Concise version (1.5k chars, ~70% token savings)")
            except Exception as e:
                print(f"⚠️  Claude API initialization failed: {e}")
                print("   Falling back to mock agent")
                self.g3_decision = G3MockDecisionAgent(config={
                    'verbose': False,
                    'debug_rejections': self.debug_rejections
                })
                self.use_claude_api = False
        else:
            self.g3_decision = G3MockDecisionAgent(config={
                'verbose': False,
                'debug_rejections': self.debug_rejections
            })
            print("✓ Using Mock Agent (rule-based) - 0 tokens used!")

        # Risk profile
        self.risk_profile = {
            'max_dd_pct': 5.0,
            'max_daily_loss_pct': 3.0,
            'max_open_trades': 2,
            'min_confidence': 0.70,
            'min_rr_ratio': 2.0,
            'blocked_conditions': [],
            'risk_per_trade_pct': 1.5,
            'min_lot': 0.01,
            'max_lot': 1.00
        }

        # Account state
        self.account_balance = 10000.0  # $10,000 starting balance
        self.daily_pnl = 0.0
        self.total_pnl = 0.0

        # Results
        self.results = {
            'total_candles': 0,
            'g1_candidates': 0,
            'g2_passed': 0,
            'g3_decisions': 0,
            'guardian_approved': 0,
            'guardian_blocked_clustering': 0,
            'guardian_blocked_cooldown': 0,
            'trades': [],
            'win_count': 0,
            'loss_count': 0,
            'be_count': 0,
            'timeout_count': 0,
            'total_pnl': 0.0,
            'condition_stats': {},
            'pattern_stats': {},
            'rsi_zone_stats': {},
            'session_stats': {}
        }

        # Anti-clustering tracking
        self.last_trade_time = {}  # {condition: timestamp}
        self.trades_per_condition_hour = {}  # {(condition, hour): count}
        self.last_sl_hit_time = None  # Cooldown after SL hit
        self.last_any_trade_time = None  # Global cooldown
        self.cooldown_minutes = 15  # Minutes to wait after SL hit
        self.global_cooldown_minutes = 10  # Minutes between ANY trades
        self.max_trades_per_condition_hour = 2  # Max trades per condition per hour (reduced from 3)

    def run(self, start_date: datetime, end_date: datetime, symbol: str = 'XAUUSD'):
        """
        Run full backtest

        Args:
            start_date: Start date
            end_date: End date
            symbol: Trading symbol
        """
        print(f"\n{'='*70}")
        print(f"FULL BACKTEST - Complete Pipeline (G1→G2→G3→G3b→G3c)")
        print(f"{'='*70}")
        print(f"Symbol: {symbol}")
        print(f"Period: {start_date.date()} to {end_date.date()}")
        print(f"Starting Balance: ${self.account_balance:,.2f}")
        print(f"Risk per Trade: {self.risk_profile['risk_per_trade_pct']}%")
        print(f"Agent Mode: {'Claude API' if self.use_claude_api else 'Mock (rule-based)'}")
        print(f"{'='*70}\n")

        # Get data
        print(f"📊 Fetching market data...")
        with create_connector('simulate') as conn:
            market_data = conn.get_latest_candles(symbol, m5_count=600, h1_count=100)

        m5_candles = market_data['m5_ohlcv']
        h1_candles = market_data['h1_candles']

        print(f"✓ Retrieved {len(m5_candles)} M5 candles")
        print(f"✓ Retrieved {len(h1_candles)} H1 candles")

        # Process candles
        min_m5 = 100
        min_h1 = 50

        print(f"\n🔍 Running backtest...")
        print(f"   Scanning {len(m5_candles) - min_m5} candles...")

        for i in range(min_m5, len(m5_candles) - 50):  # Reserve 50 for simulation
            self.results['total_candles'] += 1

            # Get window
            m5_window = m5_candles[i-min_m5:i]
            h1_window = h1_candles[-min_h1:] if len(h1_candles) >= min_h1 else h1_candles

            current_data = {
                'm5_ohlcv': m5_window,
                'h1_candles': h1_window,
                'current_price': m5_window[-1]['close'],
                'timestamp': str(m5_window[-1]['time']),
                'symbol': symbol
            }

            # === G1: Market Scanning ===
            world_state = self.g1_scanner.scan_conditions(current_data)

            if not world_state:
                continue

            self.results['g1_candidates'] += 1

            # === G2: Quantitative Analysis ===
            confidence_data = self.g2_analyzer.analyze(world_state)

            if not confidence_data:
                continue

            self.results['g2_passed'] += 1

            # === G3: Decision (Claude API or Mock) ===
            # Validate mode: switch to Mock after max_claude_calls
            if self.validate_mode and self.use_claude_api and self.claude_calls_count >= self.max_claude_calls:
                if not hasattr(self, '_switched_to_mock'):
                    print(f"\n✓ Validation mode: Reached {self.max_claude_calls} Claude API calls")
                    print(f"  Switching to Mock Agent for remaining signals...\n")
                    self.g3_decision = G3MockDecisionAgent(config={
                        'verbose': False,
                        'debug_rejections': self.debug_rejections
                    })
                    self.use_claude_api = False
                    self._switched_to_mock = True

            # Call decision agent
            decision = self.g3_decision.decide(world_state, confidence_data)

            # Count Claude API calls
            if self.use_claude_api and decision is not None:
                self.claude_calls_count += 1

            if not decision:
                continue

            self.results['g3_decisions'] += 1

            # === Anti-Clustering Check (before G3b) ===
            from datetime import datetime, timedelta

            current_time = datetime.fromisoformat(world_state['timestamp'].replace('Z', '+00:00'))
            condition = decision['chart_condition']

            # Check 0: Global cooldown (ANY trade)
            if self.last_any_trade_time:
                time_since_any = (current_time - self.last_any_trade_time).total_seconds() / 60
                if time_since_any < self.global_cooldown_minutes:
                    if self.verbose:
                        print(f"   ⏸️  Global cooldown: {time_since_any:.1f}/{self.global_cooldown_minutes} min since last trade")
                    self.results['guardian_blocked_cooldown'] += 1
                    continue

            # Check 1: Cooldown after SL hit (stricter)
            if self.last_sl_hit_time:
                time_since_sl = (current_time - self.last_sl_hit_time).total_seconds() / 60
                if time_since_sl < self.cooldown_minutes:
                    if self.verbose:
                        print(f"   ⏸️  SL cooldown active: {time_since_sl:.1f}/{self.cooldown_minutes} min since last SL")
                    self.results['guardian_blocked_cooldown'] += 1
                    continue

            # Check 2: Max trades per condition per hour
            current_hour = current_time.replace(minute=0, second=0, microsecond=0)
            hour_key = (condition, current_hour)

            if hour_key in self.trades_per_condition_hour:
                if self.trades_per_condition_hour[hour_key] >= self.max_trades_per_condition_hour:
                    if self.verbose:
                        print(f"   ⏸️  Max trades reached: {self.trades_per_condition_hour[hour_key]}/{self.max_trades_per_condition_hour} for {condition} this hour")
                    self.results['guardian_blocked_clustering'] += 1
                    continue

            # Check 3: Minimum time between same condition trades (5 minutes)
            if condition in self.last_trade_time:
                time_since_last = (current_time - self.last_trade_time[condition]).total_seconds() / 60
                if time_since_last < 5.0:
                    if self.verbose:
                        print(f"   ⏸️  Too soon: {time_since_last:.1f} min since last {condition} trade")
                    self.results['guardian_blocked_clustering'] += 1
                    continue

            # === G3b: Money Management ===
            lot = calculate_lot_size(decision, self.account_balance, self.risk_profile)
            decision['lot'] = lot

            # === G3c: Guardian ===
            account_state = {
                'balance': self.account_balance,
                'daily_pnl_pct': (self.daily_pnl / self.account_balance) * 100,
                'total_dd_pct': 0.0,  # Simplified for backtest
                'open_trades': 0,  # Simplified - no tracking of open positions
                'news_active': world_state.get('news_flag', False)
            }

            guardian_result = guardian_check(decision, lot, account_state, self.risk_profile)

            if not guardian_result['approved']:
                if self.verbose:
                    print(f"   ⏭  Guardian blocked: {guardian_result['reason']}")
                continue

            self.results['guardian_approved'] += 1

            # === Simulated Execution ===
            subsequent_candles = m5_candles[i:i+50]

            result, pnl, exit_price, close_reason, duration = calculate_simulated_result(
                decision, subsequent_candles
            )

            # Update stats
            if result == 'WIN':
                self.results['win_count'] += 1
            elif result == 'LOSS':
                self.results['loss_count'] += 1
            elif result == 'BE':
                self.results['be_count'] += 1
            elif result == 'TIMEOUT':
                self.results['timeout_count'] += 1

            self.total_pnl += pnl
            self.results['total_pnl'] = self.total_pnl
            self.account_balance += pnl

            # Record trade
            trade = {
                'timestamp': world_state['timestamp'],
                'condition': decision['chart_condition'],
                'pattern': decision['pattern'],
                'action': decision['action'],
                'rsi': world_state['rsi'],
                'rsi_zone': world_state['rsi_zone'],
                'h1_trend': world_state['h1_trend'],
                'session': world_state['session'],
                'confidence': confidence_data['confidence'],
                'entry': decision['entry'],
                'sl': decision['sl'],
                'tp1': decision['tp1'],
                'lot': lot,
                'result': result,
                'pnl': pnl,
                'exit_price': exit_price,
                'close_reason': close_reason,
                'duration_candles': duration
            }

            self.results['trades'].append(trade)

            # Update distribution stats
            self._update_stats(trade)

            # Update anti-clustering tracking
            self.last_trade_time[condition] = current_time
            self.last_any_trade_time = current_time  # Global tracking

            # Track trades per condition per hour
            if hour_key not in self.trades_per_condition_hour:
                self.trades_per_condition_hour[hour_key] = 0
            self.trades_per_condition_hour[hour_key] += 1

            # Update cooldown if SL hit
            if close_reason == 'SL_HIT':
                self.last_sl_hit_time = current_time

            # Progress
            if self.results['guardian_approved'] % 10 == 0:
                print(f"   Trades: {self.results['guardian_approved']} | "
                      f"Win: {self.results['win_count']} | "
                      f"Loss: {self.results['loss_count']} | "
                      f"P&L: ${self.total_pnl:.2f}")

        return self.results

    def _update_stats(self, trade: Dict):
        """Update distribution statistics"""
        result = trade['result']
        condition = trade['condition']
        pattern = trade['pattern']
        rsi_zone = trade['rsi_zone']
        session = trade['session']

        # Condition stats
        if condition not in self.results['condition_stats']:
            self.results['condition_stats'][condition] = {'win': 0, 'loss': 0, 'total': 0}

        self.results['condition_stats'][condition]['total'] += 1
        if result == 'WIN':
            self.results['condition_stats'][condition]['win'] += 1
        elif result == 'LOSS':
            self.results['condition_stats'][condition]['loss'] += 1

        # Pattern stats
        if pattern not in self.results['pattern_stats']:
            self.results['pattern_stats'][pattern] = {'win': 0, 'loss': 0, 'total': 0}

        self.results['pattern_stats'][pattern]['total'] += 1
        if result == 'WIN':
            self.results['pattern_stats'][pattern]['win'] += 1
        elif result == 'LOSS':
            self.results['pattern_stats'][pattern]['loss'] += 1

        # RSI zone stats
        if rsi_zone not in self.results['rsi_zone_stats']:
            self.results['rsi_zone_stats'][rsi_zone] = {'win': 0, 'loss': 0, 'total': 0}

        self.results['rsi_zone_stats'][rsi_zone]['total'] += 1
        if result == 'WIN':
            self.results['rsi_zone_stats'][rsi_zone]['win'] += 1
        elif result == 'LOSS':
            self.results['rsi_zone_stats'][rsi_zone]['loss'] += 1

        # Session stats
        if session not in self.results['session_stats']:
            self.results['session_stats'][session] = {'win': 0, 'loss': 0, 'total': 0}

        self.results['session_stats'][session]['total'] += 1
        if result == 'WIN':
            self.results['session_stats'][session]['win'] += 1
        elif result == 'LOSS':
            self.results['session_stats'][session]['loss'] += 1

    def print_summary(self):
        """Print detailed backtest summary"""
        print(f"\n{'='*70}")
        print(f"BACKTEST RESULTS")
        print(f"{'='*70}\n")

        total_trades = self.results['guardian_approved']
        win_count = self.results['win_count']
        loss_count = self.results['loss_count']
        total_pnl = self.results['total_pnl']

        # Overall stats
        print(f"📊 Pipeline Stats:")
        print(f"   Candles scanned: {self.results['total_candles']}")
        print(f"   G1 candidates: {self.results['g1_candidates']}")
        print(f"   G2 passed: {self.results['g2_passed']}")
        print(f"   G3 decisions: {self.results['g3_decisions']}")

        # Anti-clustering stats
        clustering_blocked = self.results.get('guardian_blocked_clustering', 0)
        cooldown_blocked = self.results.get('guardian_blocked_cooldown', 0)
        if clustering_blocked > 0 or cooldown_blocked > 0:
            print(f"\n   🛡️  Anti-Overtrading:")
            if clustering_blocked > 0:
                print(f"      Blocked (clustering): {clustering_blocked}")
            if cooldown_blocked > 0:
                print(f"      Blocked (cooldown): {cooldown_blocked}")

        print(f"   Guardian approved: {self.results['guardian_approved']}")

        print(f"\n💰 Trading Performance:")
        print(f"   Total Trades: {total_trades}")

        if total_trades > 0:
            win_rate = (win_count / total_trades) * 100
            print(f"   Win: {win_count} ({win_rate:.1f}%)")
            print(f"   Loss: {loss_count} ({(loss_count/total_trades)*100:.1f}%)")
            print(f"   BE: {self.results['be_count']}")
            print(f"   Timeout: {self.results['timeout_count']}")

            print(f"\n   Total P&L: ${total_pnl:,.2f}")
            print(f"   Starting Balance: $10,000.00")
            print(f"   Final Balance: ${self.account_balance:,.2f}")
            print(f"   ROI: {(total_pnl/10000)*100:.2f}%")

            if total_trades > 0:
                avg_win = sum(t['pnl'] for t in self.results['trades'] if t['result'] == 'WIN') / max(win_count, 1)
                avg_loss = sum(abs(t['pnl']) for t in self.results['trades'] if t['result'] == 'LOSS') / max(loss_count, 1)
                print(f"   Avg Win: ${avg_win:.2f}")
                print(f"   Avg Loss: ${avg_loss:.2f}")

                if avg_loss > 0:
                    profit_factor = avg_win * win_count / (avg_loss * loss_count) if loss_count > 0 else 999
                    print(f"   Profit Factor: {profit_factor:.2f}")

            # Best/Worst trades
            if self.results['trades']:
                best_trade = max(self.results['trades'], key=lambda x: x['pnl'])
                worst_trade = min(self.results['trades'], key=lambda x: x['pnl'])

                print(f"\n   Best Trade: ${best_trade['pnl']:.2f} ({best_trade['condition']} + {best_trade['pattern']})")
                print(f"   Worst Trade: ${worst_trade['pnl']:.2f} ({worst_trade['condition']} + {worst_trade['pattern']})")

            # Distribution analysis
            self._print_distribution_stats()

        else:
            print(f"   ⚠️  No trades executed")

        print(f"\n{'='*70}\n")

    def _print_distribution_stats(self):
        """Print distribution statistics"""
        print(f"\n📈 Performance by Condition:")
        for cond, stats in sorted(self.results['condition_stats'].items(),
                                   key=lambda x: x[1]['total'], reverse=True):
            total = stats['total']
            wins = stats['win']
            win_rate = (wins / total * 100) if total > 0 else 0
            print(f"   {cond:20s}: {wins:2d}/{total:2d} ({win_rate:5.1f}%)")

        print(f"\n📊 Performance by Pattern:")
        for pattern, stats in sorted(self.results['pattern_stats'].items(),
                                      key=lambda x: x[1]['total'], reverse=True):
            total = stats['total']
            wins = stats['win']
            win_rate = (wins / total * 100) if total > 0 else 0
            print(f"   {pattern:20s}: {wins:2d}/{total:2d} ({win_rate:5.1f}%)")

        print(f"\n🎯 Performance by RSI Zone:")
        for zone, stats in sorted(self.results['rsi_zone_stats'].items(),
                                  key=lambda x: x[1]['total'], reverse=True):
            total = stats['total']
            wins = stats['win']
            win_rate = (wins / total * 100) if total > 0 else 0
            print(f"   {zone:20s}: {wins:2d}/{total:2d} ({win_rate:5.1f}%)")

        print(f"\n⏰ Performance by Session:")
        for session, stats in sorted(self.results['session_stats'].items(),
                                     key=lambda x: x[1]['total'], reverse=True):
            total = stats['total']
            wins = stats['win']
            win_rate = (wins / total * 100) if total > 0 else 0
            print(f"   {session:20s}: {wins:2d}/{total:2d} ({win_rate:5.1f}%)")

    def save_results(self, filename: str = 'backtest/results/full_backtest.json'):
        """Save results to JSON"""
        os.makedirs('backtest/results', exist_ok=True)

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False, default=str)

        print(f"✓ Results saved to {filename}")


def main():
    """Run full backtest"""
    from dotenv import load_dotenv
    load_dotenv()

    # Date range (last 30 days)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)

    # Run backtest with Claude API
    bt = FullBacktest(use_claude_api=True, verbose=False)
    results = bt.run(start_date, end_date)

    # Print summary
    bt.print_summary()

    # Save results
    bt.save_results()


if __name__ == "__main__":
    main()
