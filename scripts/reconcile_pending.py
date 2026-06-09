"""Reconcile orphan PENDING trades against MT5.

Use when the bot tracker, Sheets, or LocalDB still show PENDING for orders
that MT5 has already closed (or never accepted). Compares each PENDING row in
`traider_sim.db` against MT5's open positions + history, then updates the row
(and the matching Sheets row) to reflect reality.

Run with `python scripts/reconcile_pending.py`. Add `--dry-run` to preview
without writing.
"""
from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Make project root importable so we can reuse SheetsLogger
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger("reconcile")


def _connect_mt5():
    try:
        import MetaTrader5 as mt5
    except ImportError:
        log.error("MetaTrader5 module not installed")
        return None
    if not mt5.initialize():
        log.error(f"mt5.initialize() failed: {mt5.last_error()}")
        return None
    return mt5


def _find_in_history(mt5, trade_id: str, lookback_hours: int = 48) -> dict | None:
    """Search MT5 history deals (last N hours) for an entry deal whose comment
    matches the trade_id. Returns the matched position dict or None.

    Many brokers truncate the order comment to 16 chars even when MT5 spec
    allows 31, so we match by prefix: the stored comment is the leading
    substring of our trade_id."""
    from_dt = datetime.now() - timedelta(hours=lookback_hours)
    deals = mt5.history_deals_get(from_dt, datetime.now())
    if not deals:
        return None

    def _matches(stored: str) -> bool:
        stored = (stored or "").strip()
        if not stored:
            return False
        return stored == trade_id or trade_id.startswith(stored)

    entry = next((d for d in deals if _matches(d.comment)), None)
    if entry is None:
        return None
    position_id = entry.position_id
    pos_deals = [d for d in deals if d.position_id == position_id]
    if len(pos_deals) < 2:
        # Entry exists but no close yet — position should still be open
        return {"position_id": position_id, "still_open": True}
    close_deal = pos_deals[-1]
    pnl = sum(float(d.profit) for d in pos_deals)
    return {
        "position_id": position_id,
        "still_open": False,
        "close_price": float(close_deal.price),
        "close_time": datetime.fromtimestamp(close_deal.time).isoformat(),
        "pnl": round(pnl, 2),
        "result": "WIN" if pnl > 0 else "LOSS",
        "close_reason": "TP_HIT" if pnl > 0 else "SL_HIT",
    }


def _in_open_positions(mt5, trade_id: str) -> bool:
    positions = mt5.positions_get()
    if not positions:
        return False
    for p in positions:
        c = (p.comment or "").strip()
        if c and (c == trade_id or trade_id.startswith(c)):
            return True
    return False


def reconcile(db_path: str, dry_run: bool = False) -> None:
    if not os.path.exists(db_path):
        log.error(f"DB not found: {db_path}")
        return
    mt5 = _connect_mt5()
    if mt5 is None:
        return

    con = sqlite3.connect(db_path)
    rows = con.execute(
        "SELECT trade_id, plan_id, timestamp_open, action, entry_price, sl_price, tp_price, lot_size "
        "FROM trades WHERE result = 'PENDING' ORDER BY timestamp_open"
    ).fetchall()
    if not rows:
        log.info("No PENDING rows in DB — nothing to reconcile")
        return

    log.info(f"Found {len(rows)} PENDING row(s) in {db_path}")

    # Try Sheets too (best effort — skip if creds missing or SHEETS_ENABLED=false)
    sheets = None
    try:
        from agents.g4_sheets_logger import SheetsLogger
        sheets = SheetsLogger()
        if not sheets.enabled:
            sheets = None
    except Exception as e:
        log.warning(f"Sheets logger unavailable: {e}")
        sheets = None

    updates = 0
    for r in rows:
        trade_id, plan_id, ts_open, action, entry, sl, tp, lot = r
        log.info(f"\n[{trade_id}] action={action} entry={entry} sl={sl} tp={tp} opened={ts_open}")

        if _in_open_positions(mt5, trade_id):
            log.info("  ✓ Still OPEN in MT5 — leaving as PENDING")
            continue

        hist = _find_in_history(mt5, trade_id)
        if hist is None:
            log.warning("  ⚠️  Not in open positions and not in 48h history — likely rejected at open or expired.")
            log.warning("     Marking as CANCELLED (no pnl).")
            if not dry_run:
                con.execute(
                    "UPDATE trades SET result=?, close_reason=?, timestamp_close=? WHERE trade_id=?",
                    ("CANCELLED", "BROKER_REJECT_OR_EXPIRE", datetime.now().isoformat(), trade_id),
                )
                con.commit()
                if sheets:
                    try:
                        sheets.update_order_close(
                            trade_id=trade_id, result="CANCELLED", close_price=0.0,
                            close_reason="BROKER_REJECT_OR_EXPIRE", pnl_usd=0.0,
                            timestamp_close=datetime.now().isoformat(),
                        )
                    except Exception as e:
                        log.error(f"  Sheets update failed: {e}")
                updates += 1
            continue

        if hist.get("still_open"):
            log.info(f"  ✓ Entry found in history (pos={hist['position_id']}) but no close deal yet — leaving PENDING")
            continue

        log.info(
            f"  ❎ Closed in MT5: {hist['result']} pnl={hist['pnl']:+.2f} "
            f"@ {hist['close_price']} on {hist['close_time']}"
        )
        if not dry_run:
            con.execute(
                "UPDATE trades SET result=?, close_reason=?, close_price=?, timestamp_close=?, pnl_usd=? "
                "WHERE trade_id=?",
                (hist['result'], hist['close_reason'], hist['close_price'],
                 hist['close_time'], hist['pnl'], trade_id),
            )
            con.commit()
            if sheets:
                try:
                    sheets.update_order_close(
                        trade_id=trade_id, result=hist['result'],
                        close_price=hist['close_price'], close_reason=hist['close_reason'],
                        pnl_usd=hist['pnl'], timestamp_close=hist['close_time'],
                    )
                except Exception as e:
                    log.error(f"  Sheets update failed: {e}")
            updates += 1

    # Clear active_plan_id from Sheets portfolio_state if nothing is open
    if sheets and not dry_run:
        try:
            ps = sheets.get_portfolio_state() or {}
            still_pending = con.execute("SELECT COUNT(*) FROM trades WHERE result='PENDING'").fetchone()[0]
            if still_pending == 0 and ps.get('active_plan_id'):
                log.info(f"\nClearing active_plan_id={ps.get('active_plan_id')} (no PENDING rows left)")
                ps['active_plan_id'] = ''
                ps['open_plans_count'] = 0
                ps['total_risk_pct'] = 0.0
                ps['open_orders_count'] = 0
                ps['total_open_lot'] = 0.0
                sheets.update_portfolio_state(ps)
        except Exception as e:
            log.warning(f"Portfolio state cleanup failed: {e}")

    con.close()
    log.info(f"\nDone. {updates} row(s) updated. dry_run={dry_run}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="traider_sim.db", help="LocalDB path (default: traider_sim.db)")
    p.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = p.parse_args()
    reconcile(args.db, dry_run=args.dry_run)
