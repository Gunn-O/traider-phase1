"""
Quick Backtest - สำหรับทดสอบ pipeline รวดเร็ว

จำกัดจำนวน candles เพื่อให้รันเร็ว
แสดงผลละเอียดทุก trade
"""

from backtest_full import FullBacktest
from datetime import datetime, timedelta
import json


def main():
    """Run quick backtest with limited candles"""
    from dotenv import load_dotenv
    load_dotenv()

    print("\n" + "="*70)
    print("QUICK BACKTEST - Limited Candles for Fast Testing")
    print("="*70)

    # Create backtest instance
    # ใช้ Mock Agent ก่อนเพื่อความรวดเร็ว
    # เปลี่ยนเป็น use_claude_api=True เมื่อต้องการทดสอบ Claude API
    use_claude = input("\nUse Claude API? (y/n, default=n): ").strip().lower() == 'y'

    bt = FullBacktest(use_claude_api=use_claude, verbose=True)

    # Override: scan only 100 candles for quick test
    print(f"\n📊 Fetching market data...")
    from utils import create_connector

    with create_connector('simulate') as conn:
        market_data = conn.get_latest_candles('XAUUSD', m5_count=200, h1_count=50)

    m5_candles = market_data['m5_ohlcv']
    h1_candles = market_data['h1_candles']

    print(f"✓ Retrieved {len(m5_candles)} M5 candles (will scan last 100)")
    print(f"✓ Retrieved {len(h1_candles)} H1 candles")

    # Manual scan (simplified)
    print(f"\n🔍 Scanning candles...")

    min_m5 = 100
    trades_found = 0
    max_trades = 10  # Limit to 10 trades for quick test

    for i in range(min_m5, len(m5_candles) - 50):
        if trades_found >= max_trades:
            print(f"\n✓ Reached {max_trades} trades limit - stopping scan")
            break

        bt.results['total_candles'] += 1

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
        world_state = bt.g1_scanner.scan_conditions(current_data)
        if not world_state:
            continue

        bt.results['g1_candidates'] += 1

        # G2
        confidence_data = bt.g2_analyzer.analyze(world_state)
        if not confidence_data:
            continue

        bt.results['g2_passed'] += 1

        # G3
        decision = bt.g3_decision.decide(world_state, confidence_data)
        if not decision:
            continue

        bt.results['g3_decisions'] += 1

        # G3b
        from agents.g3_money_management import calculate_lot_size
        lot = calculate_lot_size(decision, bt.account_balance, bt.risk_profile)
        decision['lot'] = lot

        # G3c
        from agents.g3_risk_gate import guardian_check
        account_state = {
            'balance': bt.account_balance,
            'daily_pnl_pct': 0,
            'total_dd_pct': 0,
            'open_trades': 0,
            'news_active': False
        }

        guardian_result = guardian_check(decision, lot, account_state, bt.risk_profile)

        if not guardian_result['approved']:
            print(f"\n⏭  Guardian blocked: {guardian_result['reason']}")
            continue

        bt.results['guardian_approved'] += 1
        trades_found += 1

        # Simulated Execution
        from utils.simulated_execution import calculate_simulated_result

        subsequent_candles = m5_candles[i:i+50]
        result, pnl, exit_price, close_reason, duration = calculate_simulated_result(
            decision, subsequent_candles
        )

        # Update stats
        if result == 'WIN':
            bt.results['win_count'] += 1
        elif result == 'LOSS':
            bt.results['loss_count'] += 1

        bt.total_pnl += pnl
        bt.results['total_pnl'] = bt.total_pnl
        bt.account_balance += pnl

        # Print trade details
        print(f"\n{'='*70}")
        print(f"TRADE #{trades_found}")
        print(f"{'='*70}")
        print(f"📍 Entry:")
        print(f"   Time: {world_state['timestamp']}")
        print(f"   Condition: {decision['chart_condition']}")
        print(f"   Pattern: {decision['pattern']}")
        print(f"   Action: {decision['action']}")
        print(f"   RSI: {world_state['rsi']:.1f} ({world_state['rsi_zone']})")
        print(f"   H1 Trend: {world_state['h1_trend']}")
        print(f"   Confidence: {confidence_data['confidence']:.3f}")

        print(f"\n💰 Trade Setup:")
        print(f"   Entry: ${decision['entry']:.2f}")
        print(f"   SL: ${decision['sl']:.2f}")
        print(f"   TP1/2/3: ${decision['tp1']:.2f} / ${decision['tp2']:.2f} / ${decision['tp3']:.2f}")
        print(f"   Lot: {lot}")

        rr = abs(decision['tp1'] - decision['entry']) / abs(decision['entry'] - decision['sl'])
        print(f"   R:R: 1:{rr:.2f}")

        print(f"\n📊 Result:")
        print(f"   Status: {result}")
        print(f"   Exit: ${exit_price:.2f}")
        print(f"   Reason: {close_reason}")
        print(f"   Duration: {duration} candles ({duration*5} min)")
        print(f"   P&L: ${pnl:.2f}")
        print(f"   Balance: ${bt.account_balance:.2f}")

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
    bt.print_summary()

    # Ask to save
    if bt.results['trades']:
        save = input("\nSave results? (y/n, default=n): ").strip().lower() == 'y'
        if save:
            bt.save_results('backtest/results/quick_backtest.json')


if __name__ == "__main__":
    main()
