"""
Signal-only backtest — bypass G2/G3 pipeline, test raw strategy.find_signal()

Loop bar-by-bar from MT5 historical data, call strategies.{mountain,mai_ruay}.find_signal()
without any pipeline filter (no 1-plan-at-a-time, no R:R filter, no duplicate check).

Output: trade list ที่ใช้เทียบกับ TV pinescript backtest ตรง ๆ ได้

Usage:
    python scripts/signal_only_backtest.py --symbol XAUUSDc --tf M5 \
           --start 2026-04-01 --end 2026-04-30 --pattern MAI_RUAY \
           --portfolio 1000

ผลคือ stdout table + ตัวเลือก --csv path/to/file เพื่อบันทึก
"""
from __future__ import annotations
import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

# Allow import from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

import MetaTrader5 as mt5  # noqa: E402
from utils.xauusd_signal import OHLC  # noqa: E402
from strategies import mountain, mai_ruay  # noqa: E402

TF_MAP = {
    'M1':  mt5.TIMEFRAME_M1,
    'M5':  mt5.TIMEFRAME_M5,
    'M15': mt5.TIMEFRAME_M15,
    'M30': mt5.TIMEFRAME_M30,
    'H1':  mt5.TIMEFRAME_H1,
    'H4':  mt5.TIMEFRAME_H4,
}

STRATEGY_MAP = {
    'MOUNTAIN': mountain.find_signal,
    'MAI_RUAY': mai_ruay.find_signal,
}


def fetch_bars(symbol: str, tf: str, start: datetime, end: datetime) -> list[OHLC]:
    if not mt5.initialize(path=os.getenv('MT5_TERMINAL_PATH') or None):
        print(f"❌ MT5 init failed: {mt5.last_error()}")
        sys.exit(1)
    rates = mt5.copy_rates_range(symbol, TF_MAP[tf], start, end)
    mt5.shutdown()
    if rates is None or len(rates) == 0:
        print(f"❌ No bars returned for {symbol} {tf} {start}–{end}")
        sys.exit(1)
    bars = []
    for i, r in enumerate(rates):
        bars.append(OHLC(
            time=str(datetime.fromtimestamp(r['time'])),
            open=float(r['open']),
            high=float(r['high']),
            low=float(r['low']),
            close=float(r['close']),
            bar_num=i + 1,
        ))
    return bars


def simulate_outcome(bars: list[OHLC], entry_idx: int, signal) -> dict:
    """Forward-walk จาก entry bar → ดูว่า hit SL หรือ TP ก่อน"""
    sl, tp = signal.sl, signal.tp_order
    is_buy = (signal.direction == 'BUY')
    for k in range(entry_idx + 1, len(bars)):
        b = bars[k]
        if is_buy:
            if b.low <= sl:
                return {'result': 'LOSS', 'close_idx': k, 'close_price': sl,
                        'close_time': b.time, 'pnl_pip': -signal.risk_pip}
            if b.high >= tp:
                return {'result': 'WIN', 'close_idx': k, 'close_price': tp,
                        'close_time': b.time, 'pnl_pip': abs(tp - signal.entry) * 100}
        else:  # SELL
            if b.high >= sl:
                return {'result': 'LOSS', 'close_idx': k, 'close_price': sl,
                        'close_time': b.time, 'pnl_pip': -signal.risk_pip}
            if b.low <= tp:
                return {'result': 'WIN', 'close_idx': k, 'close_price': tp,
                        'close_time': b.time, 'pnl_pip': abs(signal.entry - tp) * 100}
    return {'result': 'OPEN', 'close_idx': None, 'close_price': None,
            'close_time': None, 'pnl_pip': 0}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--symbol', default='XAUUSDc')
    p.add_argument('--tf', default='M5', choices=list(TF_MAP))
    p.add_argument('--start', default='2026-04-01')
    p.add_argument('--end', default='2026-04-30')
    p.add_argument('--pattern', default='MAI_RUAY', choices=list(STRATEGY_MAP) + ['BOTH'])
    p.add_argument('--portfolio', type=float, default=1000.0)
    p.add_argument('--csv', default=None, help='Optional path to write CSV output')
    p.add_argument('--no-dedupe', action='store_true',
                   help='ไม่ skip signal ซ้ำที่ entry/sl/tp ใกล้เคียง (default: skip)')
    p.add_argument('--cooldown-bars', type=int, default=0,
                   help='Skip signal ใหม่ถ้าห่างจาก signal ก่อน < N bars (per pattern). '
                        'Default 0 = ไม่ใช้ cooldown. แนะนำ 30 สำหรับ M1, 6 สำหรับ M5')
    args = p.parse_args()

    start_dt = datetime.strptime(args.start, '%Y-%m-%d')
    end_dt   = datetime.strptime(args.end,   '%Y-%m-%d')

    print(f"\n=== Signal-Only Backtest ===")
    print(f"  symbol    : {args.symbol}")
    print(f"  timeframe : {args.tf}")
    print(f"  period    : {args.start} → {args.end}")
    print(f"  pattern   : {args.pattern}")
    print(f"  portfolio : ${args.portfolio:,.0f}")
    print()

    bars = fetch_bars(args.symbol, args.tf, start_dt, end_dt)
    print(f"  bars fetched: {len(bars)}")
    print()

    patterns_to_test = [args.pattern] if args.pattern != 'BOTH' else ['MOUNTAIN', 'MAI_RUAY']
    all_trades = []

    for pat in patterns_to_test:
        find_fn = STRATEGY_MAP[pat]
        trades = []
        last_sig_key = None
        last_open_idx = -10**9  # bar idx ของ signal ก่อนหน้า (per pattern)

        # Walk bar-by-bar starting from min 55 bars (R55 window)
        for i in range(55, len(bars)):
            sub = bars[:i + 1]
            sig = find_fn(sub, portfolio=args.portfolio)
            if sig is None:
                continue

            # (a) Cooldown dedupe — Option B: skip ถ้าห่าง signal ก่อน < N bars
            if args.cooldown_bars > 0 and (i - last_open_idx) < args.cooldown_bars:
                continue

            # (b) Exact-match dedupe — skip signal เดิมเป๊ะที่ออกซ้ำแบบ bar ติดกัน
            sig_key = (round(sig.entry, 2), round(sig.sl, 2), round(sig.tp_order, 2), sig.direction)
            if not args.no_dedupe and sig_key == last_sig_key:
                continue
            last_sig_key = sig_key
            last_open_idx = i

            # Simulate forward
            outcome = simulate_outcome(bars, i, sig)
            trades.append({
                'pattern': pat,
                'open_time': bars[i].time,
                'direction': sig.direction,
                'entry': round(sig.entry, 3),
                'sl': round(sig.sl, 3),
                'tp_ref': round(sig.tp_ref, 3),
                'tp_order': round(sig.tp_order, 3),
                'rr': round(sig.rr, 2),
                'risk_pip': round(sig.risk_pip, 1),
                'reward_pip': round(sig.reward_pip, 1),
                'lot': sig.lot,
                'result': outcome['result'],
                'close_time': outcome['close_time'],
                'close_price': outcome['close_price'],
                'pnl_pip': round(outcome['pnl_pip'], 1),
                'pnl_usd': round(outcome['pnl_pip'] * sig.lot, 2),
            })

        all_trades.extend(trades)

        wins = sum(1 for t in trades if t['result'] == 'WIN')
        losses = sum(1 for t in trades if t['result'] == 'LOSS')
        opens = sum(1 for t in trades if t['result'] == 'OPEN')
        total = len(trades)
        wr = wins / max(wins + losses, 1) * 100
        net_pip = sum(t['pnl_pip'] for t in trades)
        net_usd = sum(t['pnl_usd'] for t in trades)

        print(f"--- {pat} ({args.tf}) ---")
        print(f"  signals  : {total}  (WIN={wins}, LOSS={losses}, OPEN={opens})")
        print(f"  win rate : {wr:.1f}% (closed {wins+losses}/{total})")
        print(f"  net pip  : {net_pip:+.0f}")
        print(f"  net USD  : {net_usd:+.2f}")
        print()

    # Print first 20 trades
    print(f"=== First 20 trades ===")
    print(f"  {'#':>3} {'open_time':<19} {'pattern':<10} {'dir':<4} {'entry':>9} {'sl':>9} {'tp_ord':>9} {'R:R':>5} {'result':<6} {'pnl_pip':>8}")
    for i, t in enumerate(all_trades[:20], 1):
        ot = t['open_time'][:19]
        print(f"  {i:>3} {ot:<19} {t['pattern']:<10} {t['direction']:<4} {t['entry']:>9.3f} {t['sl']:>9.3f} {t['tp_order']:>9.3f} {t['rr']:>5.2f} {t['result']:<6} {t['pnl_pip']:>+8.1f}")

    # Optional CSV output
    if args.csv:
        out_path = Path(args.csv)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, 'w', newline='', encoding='utf-8') as f:
            if all_trades:
                writer = csv.DictWriter(f, fieldnames=list(all_trades[0].keys()))
                writer.writeheader()
                writer.writerows(all_trades)
        print(f"\n  CSV written: {out_path}")


if __name__ == '__main__':
    main()
