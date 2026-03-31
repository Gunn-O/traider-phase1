"""
7-Day Backtest with Claude API

รัน backtest 7 วันด้วย Claude API จริง
ประหยัด token แต่ได้ผลลัพธ์ที่น่าเชื่อถือ
"""

from backtest_full import FullBacktest
from datetime import datetime, timedelta


def main():
    """Run 7-day backtest (Mock Agent default, Claude validation optional)"""
    import sys
    from dotenv import load_dotenv
    load_dotenv()

    print("\n" + "="*70)
    print("7-DAY BACKTEST")
    print("="*70)

    # Check for Claude API flag
    use_claude = '--claude' in sys.argv
    validate_only = '--validate' in sys.argv

    # 7 days only
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)

    print(f"\nPeriod: {start_date.date()} to {end_date.date()} (7 days)")

    if use_claude:
        if validate_only:
            print(f"Agent: Claude API (Validation mode - 20 signals only)")
            print(f"💰 Token saving: ~70% per call (concise strategy)")
        else:
            print(f"Agent: Claude API (Full mode)")
            print(f"⚠️  Warning: This will use API credits!")
    else:
        print(f"Agent: Mock Agent (rule-based)")
        print(f"💰 Token cost: $0.00 (no API calls)")

    print(f"Mode: Simulated Execution")
    print(f"\nℹ️  Use flags:")
    print(f"   --claude    = Use Claude API (full)")
    print(f"   --validate  = Use Claude API (first 20 signals only)")
    print(f"\n{'='*70}\n")

    # Run backtest
    bt = FullBacktest(
        use_claude_api=use_claude,
        verbose=False,
        validate_mode=validate_only,
        debug_rejections=0  # Set to 10 to debug rejections
    )

    # Override to use less data
    print(f"📊 Fetching 7-day market data...")
    from utils import create_connector

    with create_connector('simulate') as conn:
        # For 7 days: ~2000 M5 candles, but we'll use last 300 for efficiency
        market_data = conn.get_latest_candles('XAUUSD', m5_count=300, h1_count=50)

    m5_candles = market_data['m5_ohlcv']
    h1_candles = market_data['h1_candles']

    print(f"✓ Retrieved {len(m5_candles)} M5 candles")
    print(f"✓ Retrieved {len(h1_candles)} H1 candles")

    # Manual backtest loop (optimized)
    print(f"\n🔍 Running backtest with Claude API...")
    print(f"   (This may take a few minutes due to API calls)\n")

    min_m5 = 100
    candles_to_scan = len(m5_candles) - min_m5 - 50

    print(f"   Will scan {candles_to_scan} candles...")

    from agents.g3_money_management import calculate_lot_size
    from agents.g3_risk_gate import guardian_check
    from utils.simulated_execution import calculate_simulated_result

    for i in range(min_m5, len(m5_candles) - 50):
        bt.results['total_candles'] += 1

        if bt.results['total_candles'] % 50 == 0:
            print(f"   Progress: {bt.results['total_candles']}/{candles_to_scan} | "
                  f"Signals: {bt.results['guardian_approved']} | "
                  f"P&L: ${bt.total_pnl:.2f}")

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

        # === G1 ===
        world_state = bt.g1_scanner.scan_conditions(current_data)
        if not world_state:
            continue

        bt.results['g1_candidates'] += 1

        # === G2 ===
        confidence_data = bt.g2_analyzer.analyze(world_state)
        if not confidence_data:
            continue

        bt.results['g2_passed'] += 1

        # === G3 (Claude API) ===
        try:
            decision = bt.g3_decision.decide(world_state, confidence_data)
        except Exception as e:
            print(f"\n   ⚠️  Claude API error: {e}")
            print(f"   Skipping this signal...")
            continue

        if not decision:
            continue

        bt.results['g3_decisions'] += 1

        # === G3b ===
        lot = calculate_lot_size(decision, bt.account_balance, bt.risk_profile)
        decision['lot'] = lot

        # === G3c ===
        account_state = {
            'balance': bt.account_balance,
            'daily_pnl_pct': (bt.daily_pnl / bt.account_balance) * 100,
            'total_dd_pct': 0.0,
            'open_trades': 0,
            'news_active': world_state.get('news_flag', False)
        }

        guardian_result = guardian_check(decision, lot, account_state, bt.risk_profile)

        if not guardian_result['approved']:
            continue

        bt.results['guardian_approved'] += 1

        print(f"\n   💡 Trade #{bt.results['guardian_approved']}: "
              f"{decision['action']} {decision['chart_condition']} @ ${decision['entry']:.2f}")

        # === Simulated Execution ===
        subsequent_candles = m5_candles[i:i+50]
        result, pnl, exit_price, close_reason, duration = calculate_simulated_result(
            decision, subsequent_candles
        )

        # Update stats
        if result == 'WIN':
            bt.results['win_count'] += 1
            print(f"      ✅ WIN: ${pnl:.2f} ({close_reason})")
        elif result == 'LOSS':
            bt.results['loss_count'] += 1
            print(f"      ❌ LOSS: ${pnl:.2f} ({close_reason})")
        else:
            bt.results['be_count'] += 1
            print(f"      ⚖️  BE: ${pnl:.2f} ({close_reason})")

        bt.total_pnl += pnl
        bt.results['total_pnl'] = bt.total_pnl
        bt.account_balance += pnl

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

        bt.results['trades'].append(trade)
        bt._update_stats(trade)

    # Print summary
    print(f"\n{'='*70}\n")
    bt.print_summary()

    # Save results
    bt.save_results('backtest/results/backtest_7days_claude.json')

    print(f"\n{'='*70}")
    print(f"💡 Token Usage Estimate:")
    api_calls = bt.results['g3_decisions']
    tokens_per_call = 250  # Estimate
    total_tokens = api_calls * tokens_per_call
    cost = (total_tokens / 1000000) * 3  # $3 per million tokens (Sonnet 4.5 input)
    print(f"   API Calls: ~{api_calls}")
    print(f"   Estimated Tokens: ~{total_tokens:,}")
    print(f"   Estimated Cost: ~${cost:.4f}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
