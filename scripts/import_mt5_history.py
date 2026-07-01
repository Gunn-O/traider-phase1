#!/usr/bin/env python3
"""
import_mt5_history.py — one-shot bulk import of CLOSED MT5 deals into our
per-mode LocalDB, so trade history survives MT5's ~1-month retention.

Use this to capture the existing ~1 month BEFORE a reset, and any time you want
to backfill. Idempotent: re-running never duplicates (keyed on mt5_position_id).

Usage:
    python scripts/import_mt5_history.py --mode micro --from 2026-05-10 --to 2026-06-10
    python scripts/import_mt5_history.py --mode live  --from 2026-05-10        # to = now

Reads MT5 deal history filtered by the mode's magic number, groups deals by
position_id into closed trades, and upserts into traider_{mode}.db.
"""
import os
import sys
import argparse
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import MetaTrader5 as mt5  # noqa: E402
from utils.local_db import LocalDB, db_for_mode  # noqa: E402
from agents.mt5_live_broker import MAGIC_BY_MODE  # noqa: E402


def parse_dt(s: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise SystemExit(f"bad date {s!r} — use YYYY-MM-DD or 'YYYY-MM-DD HH:MM'")


def group_closed_deals(deals, magic):
    """Group MT5 deals (filtered by magic) by position_id into closed trades."""
    our = [d for d in deals if getattr(d, "magic", 0) == magic]
    by_pos = {}
    for d in our:
        pid = int(getattr(d, "position_id", 0) or 0)
        if pid:
            by_pos.setdefault(pid, []).append(d)

    out = []
    for pid, dlist in by_pos.items():
        dlist.sort(key=lambda d: d.time)
        entry = next((d for d in dlist if getattr(d, "entry", 0) == mt5.DEAL_ENTRY_IN), dlist[0])
        exits = [d for d in dlist if getattr(d, "entry", 0) == mt5.DEAL_ENTRY_OUT]
        if not exits:
            continue  # still open
        close_deal = exits[-1]
        pnl = round(sum(float(d.profit) for d in dlist), 2)
        action = "BUY" if entry.type == mt5.DEAL_TYPE_BUY else "SELL"
        result = "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "BREAKEVEN")
        close_reason = "TP_HIT" if pnl > 0 else ("SL_HIT" if pnl < 0 else "CLOSED")
        out.append({
            "mt5_position_id": pid,
            "trade_id":     (entry.comment or "").strip(),
            "action":       action,
            "lot":          float(getattr(entry, "volume", 0.0)),
            "entry_price":  float(entry.price),
            "open_time":    datetime.fromtimestamp(entry.time).isoformat(),
            "result":       result,
            "close_price":  float(close_deal.price),
            "close_time":   datetime.fromtimestamp(close_deal.time).isoformat(),
            "close_reason": close_reason,
            "pnl":          pnl,
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=["micro", "live"], help="account mode")
    ap.add_argument("--from", dest="from_dt", required=True, help="YYYY-MM-DD[ HH:MM]")
    ap.add_argument("--to", dest="to_dt", default=None, help="YYYY-MM-DD[ HH:MM] (default: now)")
    args = ap.parse_args()

    magic = MAGIC_BY_MODE[args.mode]
    f = parse_dt(args.from_dt)
    t = parse_dt(args.to_dt) if args.to_dt else datetime.now()

    if not mt5.initialize():
        print("MT5 init failed:", mt5.last_error()); sys.exit(1)

    # ±12h widen for broker timezone offset
    deals = mt5.history_deals_get(f - timedelta(hours=12), t + timedelta(hours=12)) or []
    closed = group_closed_deals(deals, magic)
    print(f"MT5 {args.mode} (magic {magic}) closed positions in window: {len(closed)}")

    db_path = db_for_mode(args.mode)
    db = LocalDB(db_path=db_path)
    known = db.get_known_mt5_position_ids()
    inserted = updated = 0
    for d in closed:
        existed = d["mt5_position_id"] in known
        db.upsert_mt5_deal(d, bot_id=None, mode=args.mode)
        if existed:
            updated += 1
        else:
            inserted += 1
    db.close() if hasattr(db, "close") else None
    mt5.shutdown()
    print(f"✓ Imported into {db_path}: {inserted} new, {updated} already-known (idempotent)")


if __name__ == "__main__":
    main()
