"""Diagnose: log ≠ MT5 orders mismatch

Run inline on the live MT5 terminal (PowerShell + MT5 installed).
Pulls Python's LocalDB trades + MT5 actual orders/deals in the same window
and prints a side-by-side reconciliation so we can see exactly where they
diverge.

Usage:
    python diagnose_order_mismatch.py --from "2026-06-01 00:00" --to "2026-06-01 01:00"
"""
from __future__ import annotations
import argparse, sqlite3, sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import MetaTrader5 as mt5  # type: ignore
from dotenv import load_dotenv
import os

load_dotenv()

# Bot's magic numbers per mode (from agents/mt5_live_broker.py)
MAGIC_MICRO = 10002
MAGIC_LIVE  = 10003
# Default to checking BOTH unless user explicitly overrides
_env_magic = os.getenv('MT5_MAGIC')
MAGICS = [int(_env_magic)] if _env_magic else [MAGIC_MICRO, MAGIC_LIVE]
SYMBOL = os.getenv('MT5_SYMBOL', 'XAUUSDc')


def parse_dt(s: str) -> datetime:
    return datetime.strptime(s, '%Y-%m-%d %H:%M')


def fmt(d):
    return d.strftime('%H:%M:%S') if isinstance(d, datetime) else str(d)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--from', dest='from_dt', required=True)
    p.add_argument('--to', dest='to_dt', required=True)
    p.add_argument('--db', default='traider_sim.db')
    args = p.parse_args()

    f = parse_dt(args.from_dt)
    t = parse_dt(args.to_dt)

    if not mt5.initialize():
        print('MT5 init failed:', mt5.last_error())
        sys.exit(1)

    # Broker timezone offset — MT5 history queries take broker server time,
    # but DB timestamps are UTC (candle.time from MT5 already comes in UTC).
    # Convert from/to to broker time by widening the window ±12h to catch
    # any timezone offset the broker uses (Exness servers usually GMT+2/+3).
    from datetime import timedelta as _td
    f_wide = f - _td(hours=12)
    t_wide = t + _td(hours=12)
    print(f'MT5 query window (±12h timezone tolerance): {f_wide} → {t_wide}')
    print(f'Magic numbers checked: {MAGICS}')
    print(f'Symbol: {SYMBOL}')
    print()

    # ── 1. Python LocalDB trades in window ────────────────────────────
    c = sqlite3.connect(args.db)
    rows = c.execute("""
        SELECT trade_id, plan_id, timestamp_open, action, entry_price, sl_price, tp_price,
               lot_size, result, close_price, timestamp_close, pnl_usd
        FROM trades
        WHERE timestamp_open >= ? AND timestamp_open <= ?
          AND technique = 'mai_ruay'
        ORDER BY timestamp_open, plan_id, trade_id
    """, (f.isoformat(), t.isoformat())).fetchall()

    print('='*100)
    print(f'PYTHON LOG  ({args.db}, technique=mai_ruay, {fmt(f)} → {fmt(t)}):')
    print('='*100)
    for r in rows:
        print(f'  {r[2][:19]} {r[3]:4} E={r[4]:.3f} SL={r[5]:.3f} TP={r[6]:.3f} lot={r[7]:.2f} '
              f'| {r[8]:15} close={r[9] or "-":>9} pnl=${r[11] or 0:+.2f}')
        print(f'    trade_id={r[0]}  plan_id={r[1]}')

    # ── 2. MT5 orders (open + filled) in window ──────────────────────
    print()
    print('='*100)
    print(f'MT5 HISTORY ORDERS  (magics={MAGICS}, symbol={SYMBOL}, '
          f'wide={fmt(f_wide)} → {fmt(t_wide)}):')
    print('='*100)
    hist_orders = mt5.history_orders_get(f_wide, t_wide) or []
    our_orders = [o for o in hist_orders if getattr(o, 'magic', 0) in MAGICS]
    print(f'  total MT5 orders in window: {len(hist_orders)}  our: {len(our_orders)}')
    for o in our_orders:
        state = {0: 'STARTED', 1: 'PLACED', 2: 'CANCELED', 3: 'PARTIAL',
                 4: 'FILLED', 5: 'REJECTED', 6: 'EXPIRED'}.get(o.state, str(o.state))
        ot = {0: 'BUY', 1: 'SELL', 2: 'BUY_LIMIT', 3: 'SELL_LIMIT',
              4: 'BUY_STOP', 5: 'SELL_STOP'}.get(o.type, str(o.type))
        print(f'  ticket={o.ticket}  type={ot:10}  state={state:10}  '
              f'volume={o.volume_initial:.2f}  price={o.price_open:.3f}  '
              f'sl={o.sl:.3f} tp={o.tp:.3f}  comment={(o.comment or "")[:30]!r}')

    # ── 3. MT5 deals (actual fills + closes) in window ────────────────
    print()
    print('='*100)
    print(f'MT5 HISTORY DEALS  (magics={MAGICS}, wide={fmt(f_wide)} → {fmt(t_wide)}):')
    print('='*100)
    deals = mt5.history_deals_get(f_wide, t_wide) or []
    our_deals = [d for d in deals if getattr(d, 'magic', 0) in MAGICS]
    print(f'  total MT5 deals in window: {len(deals)}  our: {len(our_deals)}')
    for d in our_deals:
        entry = 'OPEN' if d.entry == 0 else 'CLOSE'
        dt = datetime.fromtimestamp(d.time)
        print(f'  {dt.strftime("%H:%M:%S")}  pos={d.position_id} order={d.order} '
              f'{entry:5} {"BUY" if d.type == 0 else "SELL":4} '
              f'volume={d.volume:.2f} price={d.price:.3f} profit=${d.profit:+.2f} '
              f'comment={(d.comment or "")[:30]!r}')

    # ── 4. Reconciliation by trade_id prefix ─────────────────────────
    print()
    print('='*100)
    print('RECONCILIATION  (Python log vs MT5 actual):')
    print('='*100)
    py_tids = {r[0] for r in rows}
    mt5_comments = set()
    for o in our_orders:
        mt5_comments.add((o.comment or '').strip())
    for d in our_deals:
        mt5_comments.add((d.comment or '').strip())

    def _matches_any(py_tid: str, mt5_set) -> bool:
        # MT5 truncates comment to 16-31 chars depending on broker
        for mc in mt5_set:
            if mc and (mc == py_tid or py_tid.startswith(mc) or mc.startswith(py_tid[:16])):
                return True
        return False

    print('\nPython trades NOT found in MT5:')
    missing_in_mt5 = [tid for tid in py_tids if not _matches_any(tid, mt5_comments)]
    if missing_in_mt5:
        for t in missing_in_mt5:
            print(f'  MISSING: {t}')
    else:
        print('  (none — all Python trades present in MT5)')

    print('\nMT5 orders/deals NOT in Python log:')
    extra = [c for c in mt5_comments if c and not any(c == p[:16] or p.startswith(c) for p in py_tids)]
    if extra:
        for c in extra:
            print(f'  EXTRA MT5: comment={c!r}')
    else:
        print('  (none — all MT5 activity tracked by Python)')

    mt5.shutdown()


if __name__ == '__main__':
    main()
