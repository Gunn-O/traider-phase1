"""
Result Viewer - แสดงผลลัพธ์ backtest แบบสวยงาม
"""

import json
import os
from datetime import datetime


def view_backtest_results(filepath='backtest/results/backtest_7days_claude.json'):
    """แสดงผลลัพธ์ backtest"""

    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        print(f"\nAvailable results:")
        results_dir = 'backtest/results'
        if os.path.exists(results_dir):
            files = [f for f in os.listdir(results_dir) if f.endswith('.json')]
            if files:
                for f in files:
                    print(f"   - {f}")
            else:
                print(f"   (no results yet)")
        return

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print("\n" + "="*70)
    print("BACKTEST RESULTS VIEWER")
    print("="*70)
    print(f"File: {filepath}")
    print("="*70 + "\n")

    # Pipeline Stats
    print("📊 Pipeline Stats:")
    print(f"   Candles scanned: {data.get('total_candles', 0):,}")
    print(f"   G1 candidates: {data.get('g1_candidates', 0):,}")
    print(f"   G2 passed: {data.get('g2_passed', 0):,}")
    print(f"   G3 decisions: {data.get('g3_decisions', 0):,}")
    print(f"   Guardian approved: {data.get('guardian_approved', 0):,}")

    # Trading Performance
    total = data.get('guardian_approved', 0)
    wins = data.get('win_count', 0)
    losses = data.get('loss_count', 0)
    be = data.get('be_count', 0)
    timeout = data.get('timeout_count', 0)
    pnl = data.get('total_pnl', 0)

    print(f"\n💰 Trading Performance:")
    print(f"   Total Trades: {total}")

    if total > 0:
        win_rate = (wins / total) * 100
        print(f"   Wins: {wins} ({win_rate:.1f}%)")
        print(f"   Losses: {losses} ({losses/total*100:.1f}%)")
        print(f"   BE: {be}")
        print(f"   Timeout: {timeout}")

        print(f"\n   Total P&L: ${pnl:,.2f}")
        print(f"   Starting Balance: $10,000.00")
        print(f"   Final Balance: ${10000 + pnl:,.2f}")
        print(f"   ROI: {(pnl/10000)*100:.2f}%")

        # Calculate avg win/loss
        trades = data.get('trades', [])
        if trades:
            winning_trades = [t for t in trades if t.get('result') == 'WIN']
            losing_trades = [t for t in trades if t.get('result') == 'LOSS']

            if winning_trades:
                avg_win = sum(t.get('pnl', 0) for t in winning_trades) / len(winning_trades)
                print(f"   Avg Win: ${avg_win:.2f}")

            if losing_trades:
                avg_loss = sum(abs(t.get('pnl', 0)) for t in losing_trades) / len(losing_trades)
                print(f"   Avg Loss: ${avg_loss:.2f}")

            # Best/Worst
            best = max(trades, key=lambda x: x.get('pnl', 0))
            worst = min(trades, key=lambda x: x.get('pnl', 0))

            print(f"\n   Best Trade: ${best.get('pnl', 0):.2f} ({best.get('condition')} + {best.get('pattern')})")
            print(f"   Worst Trade: ${worst.get('pnl', 0):.2f} ({worst.get('condition')} + {worst.get('pattern')})")

        # Distribution stats
        print(f"\n📈 Performance by Condition:")
        for cond, stats in sorted(data.get('condition_stats', {}).items(),
                                   key=lambda x: x[1]['total'], reverse=True):
            total_cond = stats['total']
            wins_cond = stats['win']
            wr = (wins_cond / total_cond * 100) if total_cond > 0 else 0
            print(f"   {cond:20s}: {wins_cond:2d}/{total_cond:2d} ({wr:5.1f}%)")

        print(f"\n📊 Performance by Pattern:")
        for pattern, stats in sorted(data.get('pattern_stats', {}).items(),
                                      key=lambda x: x[1]['total'], reverse=True):
            total_pat = stats['total']
            wins_pat = stats['win']
            wr = (wins_pat / total_pat * 100) if total_pat > 0 else 0
            print(f"   {pattern:20s}: {wins_pat:2d}/{total_pat:2d} ({wr:5.1f}%)")

        print(f"\n🎯 Performance by RSI Zone:")
        for zone, stats in sorted(data.get('rsi_zone_stats', {}).items(),
                                  key=lambda x: x[1]['total'], reverse=True):
            total_zone = stats['total']
            wins_zone = stats['win']
            wr = (wins_zone / total_zone * 100) if total_zone > 0 else 0
            print(f"   {zone:20s}: {wins_zone:2d}/{total_zone:2d} ({wr:5.1f}%)")

        print(f"\n⏰ Performance by Session:")
        for session, stats in sorted(data.get('session_stats', {}).items(),
                                     key=lambda x: x[1]['total'], reverse=True):
            total_sess = stats['total']
            wins_sess = stats['win']
            wr = (wins_sess / total_sess * 100) if total_sess > 0 else 0
            print(f"   {session:20s}: {wins_sess:2d}/{total_sess:2d} ({wr:5.1f}%)")

        # Trade list
        print(f"\n📝 All Trades:")
        for i, trade in enumerate(trades, 1):
            result_emoji = '✅' if trade.get('result') == 'WIN' else '❌'
            print(f"\n   {i}. {result_emoji} {trade.get('timestamp')} | "
                  f"{trade.get('action')} @ ${trade.get('entry'):.2f}")
            print(f"      {trade.get('condition')} + {trade.get('pattern')} | "
                  f"RSI {trade.get('rsi'):.0f} ({trade.get('rsi_zone')})")
            print(f"      Result: {trade.get('result')} | "
                  f"P&L: ${trade.get('pnl'):.2f} | "
                  f"{trade.get('close_reason')} ({trade.get('duration_candles')}c)")

    else:
        print("   ⚠️  No trades executed")

    print("\n" + "="*70 + "\n")


def list_available_results():
    """แสดงรายการไฟล์ results ทั้งหมด"""
    results_dir = 'backtest/results'

    if not os.path.exists(results_dir):
        print("No results directory found")
        return

    files = [f for f in os.listdir(results_dir) if f.endswith('.json')]

    if not files:
        print("No result files found")
        return

    print("\n" + "="*70)
    print("AVAILABLE BACKTEST RESULTS")
    print("="*70 + "\n")

    for f in sorted(files):
        filepath = os.path.join(results_dir, f)
        size = os.path.getsize(filepath)
        mtime = datetime.fromtimestamp(os.path.getmtime(filepath))

        print(f"📄 {f}")
        print(f"   Size: {size:,} bytes")
        print(f"   Modified: {mtime.strftime('%Y-%m-%d %H:%M:%S')}")

        # Quick peek
        try:
            with open(filepath, 'r') as file:
                data = json.load(file)
                trades = data.get('guardian_approved', 0)
                wins = data.get('win_count', 0)
                if trades > 0:
                    wr = (wins / trades) * 100
                    print(f"   Trades: {trades} | Win Rate: {wr:.1f}%")
        except:
            pass

        print()

    print("="*70 + "\n")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == 'list':
            list_available_results()
        else:
            view_backtest_results(sys.argv[1])
    else:
        # Try to view latest result
        results_dir = 'backtest/results'
        if os.path.exists(results_dir):
            files = sorted([f for f in os.listdir(results_dir) if f.endswith('.json')])
            if files:
                latest = os.path.join(results_dir, files[-1])
                view_backtest_results(latest)
            else:
                print("No results found. Run a backtest first!")
                print("\nUsage:")
                print("  python view_results.py              # View latest result")
                print("  python view_results.py list         # List all results")
                print("  python view_results.py <filepath>   # View specific file")
        else:
            print("No results directory found")
