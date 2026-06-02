"""
One-shot reconciliation: pull MT5 actual order/deal history for live
MaiRuay trades in a date range, compare to what Python's LocalDB +
Google Sheets recorded, and update any rows that diverge.

Why: Plan 2026-06-01 13:13 (and any prior live plan) recorded fills /
SL hits in Python that MT5 actually never executed — Python's pending-
LIMIT simulator used candle.low/high as a fill proxy but MT5 uses real
ticks, so the two diverged on fast-moving bars. The fix in commit
56deea0 prevents this going forward; this script repairs the historical
rows already written to LocalDB + Sheets.

Usage:
    python reconcile_live_trades.py --from "2026-05-01 00:00" --to "2026-06-02 00:00"

Add --dry-run to preview without writing. Add --sheets to also push the
corrections to Google Sheets (otherwise LocalDB only).

Match strategy: MT5 truncates the comment to 16 chars on most brokers,
and overwrites it with "expired [...]" / "[sl ...]" / "[tp ...]" when
the order changes state. We use the FULL trade_id from the LocalDB
trade and look up MT5 by:
  1. positions_get + history_deals_get comment-prefix match (covers
     "RT-YYYYMMDD-HHMM" prefix that MT5 keeps on entry deals).
  2. history_orders_get → match by entry price + lot + magic when the
     comment has been overwritten by expiration.
"""
from __future__ import annotations
import argparse, sqlite3, sys, os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import MetaTrader5 as mt5  # type: ignore
from dotenv import load_dotenv

load_dotenv()

# bot magic numbers (must match agents/mt5_live_broker.MAGIC_BY_MODE)
MAGIC_MICRO = 10002
MAGIC_LIVE  = 10003
MAGICS = (MAGIC_MICRO, MAGIC_LIVE)
SYMBOL = os.getenv('MT5_SYMBOL', 'XAUUSDc')


def parse_dt(s: str) -> datetime:
    return datetime.strptime(s, '%Y-%m-%d %H:%M')


def _comment_matches(stored: str, full_tid: str) -> bool:
    """MT5 stores comment truncated to ~16-31 chars; match by prefix.
    But MT5 also REWRITES the comment to 'expired [...]' / '[sl ...]' /
    '[tp ...]' on state change, so prefix match alone misses those."""
    stored = (stored or "").strip()
    if not stored:
        return False
    return stored == full_tid or full_tid.startswith(stored) or stored.startswith(full_tid[:16])


def _find_mt5_outcome(db_row: tuple, deals: list, hist_orders: list,
                     active_positions: list, active_orders: list,
                     claimed_deal_tickets: set,
                     claimed_order_tickets: set) -> dict:
    """Given a Python DB row + MT5 history snapshot, decide what happened.

    Returns a dict the caller turns into UPDATE rows:
      {'state': 'WIN' | 'LOSS' | 'CANCELLED' | 'STILL_OPEN' | 'UNKNOWN',
       'close_price': float, 'close_time': datetime, 'pnl_usd': float,
       'close_reason': 'TP_HIT' | 'SL_HIT' | 'EXPIRED' | 'OTHER',
       'mt5_fill_price': Optional[float],
       'reason_log': str}
    """
    tid = db_row[0]            # trade_id
    db_entry = db_row[3]       # entry_price the bot intended
    db_lot   = db_row[6]       # lot_size

    # 1. Is it currently open at MT5?
    for p in active_positions:
        if _comment_matches(p.comment, tid):
            return {'state': 'STILL_OPEN', 'reason_log': f'matched active position #{p.ticket}'}

    # 2. Is the pending LIMIT still queued?
    for o in active_orders:
        if _comment_matches(o.comment, tid):
            return {'state': 'STILL_OPEN', 'reason_log': f'matched active order #{o.ticket}'}

    # 3. Look for the entry deal in history. MT5 keeps the bot's comment
    #    on the OPEN deal (entry=0) until the position closes; CLOSE
    #    deals carry "[tp ...]" / "[sl ...]".
    #
    # IMPORTANT: MT5 truncates the comment to 16 chars on most brokers,
    # so all 3 entries of a multi-entry plan share the same truncated
    # comment (e.g. all "RT-20260601-1313"). Comment match alone false-
    # matches every entry to the FIRST filled deal of the plan. Solution:
    #   1. require price match within a tight tolerance (LIMIT fills at
    #      exactly the requested price; MARKET fallback fills within the
    #      spread, usually < 0.5 USD on XAU).
    #   2. among candidates, pick the one with the SMALLEST price diff,
    #      so the closest deal "wins" — covers MARKET fallback where
    #      Python requested a high LIMIT but MT5 filled at current ask.
    PRICE_TOL = 0.5  # USD ≈ 50 pip on XAU; covers spread + small slippage
    candidates = [
        d for d in deals
        if d.entry == 0
        and d.ticket not in claimed_deal_tickets   # don't double-assign
        and _comment_matches(d.comment, tid)
        and abs(d.price - float(db_entry)) < PRICE_TOL
    ]
    entry_deal = min(candidates, key=lambda d: abs(d.price - float(db_entry))) \
                 if candidates else None
    if entry_deal is not None:
        claimed_deal_tickets.add(entry_deal.ticket)
    if entry_deal is not None:
        # We filled. Find the matching CLOSE deal on the same position_id.
        position_id = entry_deal.position_id
        close_deal = next(
            (d for d in deals if d.position_id == position_id and d.entry == 1),
            None,
        )
        if close_deal is None:
            return {'state': 'STILL_OPEN',
                    'reason_log': f'entry deal #{entry_deal.ticket} found but no close deal yet',
                    'mt5_fill_price': float(entry_deal.price)}
        # Close reason from comment
        cc = (close_deal.comment or '').lower()
        if 'tp' in cc:
            close_reason = 'TP_HIT'
        elif 'sl' in cc:
            close_reason = 'SL_HIT'
        else:
            close_reason = 'OTHER'
        # WIN/LOSS by sign of position pnl
        # entry_deal.profit is 0 for the entry; close_deal carries the realized pnl
        pnl = float(close_deal.profit) + float(getattr(close_deal, 'swap', 0) or 0) \
              + float(getattr(close_deal, 'commission', 0) or 0)
        state = 'WIN' if pnl > 0 else 'LOSS'
        return {
            'state': state,
            'close_price': float(close_deal.price),
            'close_time': datetime.fromtimestamp(close_deal.time),
            'pnl_usd': round(pnl, 2),
            'close_reason': close_reason,
            'mt5_fill_price': float(entry_deal.price),
            'reason_log': f'matched entry deal #{entry_deal.ticket} + close deal #{close_deal.ticket}',
        }

    # 4. No deal — was it placed as a pending order that expired before fill?
    #    The expired/canceled history_orders carry "expired [...]" as comment,
    #    so we match by price + lot + magic instead. Same claimed-set logic
    #    so two entries that requested the same price don't claim the same
    #    expired order.
    for o in hist_orders:
        if o.ticket in claimed_order_tickets:
            continue
        if getattr(o, 'magic', 0) not in MAGICS:
            continue
        # Pending order types: 2=BUY_LIMIT, 3=SELL_LIMIT, 4=BUY_STOP, 5=SELL_STOP
        if o.type not in (2, 3, 4, 5):
            continue
        # state: 6=EXPIRED, 2=CANCELED
        if o.state not in (2, 6):
            continue
        if abs(o.price_open - float(db_entry)) > 0.01:
            continue
        if abs(o.volume_initial - float(db_lot)) > 0.001:
            continue
        claimed_order_tickets.add(o.ticket)
        return {
            'state': 'CANCELLED',
            'close_price': float(db_entry),
            'close_time': datetime.fromtimestamp(o.time_done) if o.time_done else None,
            'pnl_usd': 0.0,
            'close_reason': 'EXPIRED' if o.state == 6 else 'CANCELLED',
            'reason_log': f'matched expired/canceled order #{o.ticket} by price+lot',
        }

    return {'state': 'UNKNOWN', 'reason_log': 'no matching MT5 record found'}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--from', dest='from_dt', required=True, help='YYYY-MM-DD HH:MM')
    p.add_argument('--to',   dest='to_dt',   required=True, help='YYYY-MM-DD HH:MM')
    p.add_argument('--db',   default='traider_sim.db')
    p.add_argument('--dry-run', action='store_true', help='Show what would change, write nothing')
    p.add_argument('--sheets', action='store_true', help='Also push corrections to Google Sheets')
    args = p.parse_args()

    f = parse_dt(args.from_dt)
    t = parse_dt(args.to_dt)

    if not mt5.initialize():
        print('MT5 init failed:', mt5.last_error())
        sys.exit(1)

    # Widen window ±12h for broker timezone offset (Exness is GMT+2/+3)
    mt5_from = f - timedelta(hours=12)
    mt5_to   = t + timedelta(hours=12)

    active_positions = [p for p in (mt5.positions_get(symbol=SYMBOL) or [])
                        if getattr(p, 'magic', 0) in MAGICS]
    active_orders    = [o for o in (mt5.orders_get(symbol=SYMBOL) or [])
                        if getattr(o, 'magic', 0) in MAGICS]
    hist_orders      = [o for o in (mt5.history_orders_get(mt5_from, mt5_to) or [])
                        if getattr(o, 'magic', 0) in MAGICS]
    deals            = [d for d in (mt5.history_deals_get(mt5_from, mt5_to) or [])
                        if getattr(d, 'magic', 0) in MAGICS]

    print(f'MT5 snapshot in [{mt5_from} → {mt5_to}]:')
    print(f'  active positions: {len(active_positions)}')
    print(f'  active orders   : {len(active_orders)}')
    print(f'  history orders  : {len(hist_orders)}')
    print(f'  history deals   : {len(deals)}')
    print()

    # Pull live MaiRuay rows in the user-supplied window
    conn = sqlite3.connect(args.db)
    rows = conn.execute("""
        SELECT trade_id, plan_id, timestamp_open, entry_price, sl_price, tp_price,
               lot_size, result, close_price, timestamp_close, pnl_usd, close_reason
        FROM trades
        WHERE technique = 'mai_ruay'
          AND trade_id LIKE 'RT-%'
          AND timestamp_open >= ? AND timestamp_open <= ?
        ORDER BY timestamp_open
    """, (f.isoformat(), t.isoformat())).fetchall()

    print(f'LocalDB rows to reconcile: {len(rows)}')
    print('='*100)

    # claimed sets — MT5 truncates comments so all entries of a plan look
    # identical. Track which deal/order tickets have already been assigned
    # so two Python entries don't both grab the same MT5 fill.
    claimed_deal_tickets: set = set()
    claimed_order_tickets: set = set()

    changes = []
    for r in rows:
        tid, plan_id, t_open, db_entry, db_sl, db_tp, db_lot, db_result, db_close, t_close, db_pnl, db_reason = r
        outcome = _find_mt5_outcome(
            r, deals, hist_orders, active_positions, active_orders,
            claimed_deal_tickets, claimed_order_tickets,
        )

        # Decide: does this row need updating?
        new_state = outcome.get('state')
        if new_state in ('UNKNOWN', 'STILL_OPEN'):
            print(f'  [SKIP] {tid}  db={db_result:9} mt5={new_state}  ({outcome["reason_log"]})')
            continue

        needs_update = (
            db_result != new_state
            or (outcome.get('close_price') and abs((db_close or 0) - outcome['close_price']) > 0.001)
            or (outcome.get('pnl_usd') is not None and abs((db_pnl or 0) - outcome['pnl_usd']) > 0.01)
        )
        if not needs_update:
            print(f'  [OK]   {tid}  {db_result:9} pnl=${db_pnl:+.2f}')
            continue

        # Diff
        new_close_price = outcome.get('close_price', db_close or db_entry)
        new_close_time  = outcome.get('close_time')
        new_pnl         = outcome.get('pnl_usd', 0.0)
        new_reason      = outcome.get('close_reason', db_reason or '')

        print(f'  [FIX]  {tid}')
        print(f'         db : {db_result:9} close={db_close or 0:.3f}  pnl=${db_pnl or 0:+.2f}  reason={db_reason}')
        print(f'         mt5: {new_state:9} close={new_close_price:.3f}  pnl=${new_pnl:+.2f}  reason={new_reason}')
        print(f'         ({outcome["reason_log"]})')

        changes.append({
            'trade_id'   : tid,
            'new_result' : new_state,
            'close_price': new_close_price,
            'close_time' : new_close_time.isoformat() if new_close_time else (t_close or t_open),
            'pnl_usd'    : new_pnl,
            'close_reason': new_reason,
        })

    print()
    print(f'Rows to update: {len(changes)}')

    if not changes:
        print('Nothing to do.')
        return

    if args.dry_run:
        print('(dry-run — no writes performed)')
        return

    # Apply LocalDB updates
    print('\nUpdating LocalDB...')
    for ch in changes:
        conn.execute("""
            UPDATE trades SET
                result = ?, pnl_usd = ?, close_reason = ?,
                close_price = ?, timestamp_close = ?
            WHERE trade_id = ?
        """, (ch['new_result'], ch['pnl_usd'], ch['close_reason'],
              ch['close_price'], ch['close_time'], ch['trade_id']))
    conn.commit()
    print(f'  ✓ {len(changes)} LocalDB rows updated')

    # Optional: push to Google Sheets
    if args.sheets:
        print('\nUpdating Google Sheets...')
        from agents.g4_sheets_logger import SheetsLogger
        sl = SheetsLogger()
        if not sl.enabled:
            print('  ⚠ Sheets disabled (no credentials or env flag) — skipped')
        else:
            ok = 0
            for ch in changes:
                if sl.update_order_close(
                    ch['trade_id'], ch['new_result'], ch['close_price'],
                    ch['close_reason'], ch['pnl_usd'], ch['close_time'],
                ):
                    ok += 1
            print(f'  ✓ {ok}/{len(changes)} Sheets rows updated')

    mt5.shutdown()
    print('\nDone.')


if __name__ == '__main__':
    main()
