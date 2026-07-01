#!/usr/bin/env python3
"""
verify_consistency.py — check that our per-mode DB agrees with MT5 (and
optionally Google Sheets) BEFORE you reset/trust the data.

Compares each CLOSED trade in traider_{mode}.db against MT5 deal history (matched
by comment/trade_id prefix or mt5_position_id) and reports:
  - matched rows (result + pnl agree within tolerance)
  - mismatched rows (result/pnl/close_price differ)
  - DB rows MT5 has no record of
  - MT5 closed deals missing from our DB

Usage:
    python scripts/verify_consistency.py --mode micro
    python scripts/verify_consistency.py --mode live --from 2026-05-10 --sheets
"""
import os
import sys
import argparse
import sqlite3
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import MetaTrader5 as mt5  # noqa: E402
from utils.local_db import db_for_mode  # noqa: E402
from agents.mt5_live_broker import MAGIC_BY_MODE  # noqa: E402

PNL_TOL = 0.05  # USD


def parse_dt(s):
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise SystemExit(f"bad date {s!r}")


def group_closed_deals(deals, magic):
    our = [d for d in deals if getattr(d, "magic", 0) == magic]
    by_pos = {}
    for d in our:
        pid = int(getattr(d, "position_id", 0) or 0)
        if pid:
            by_pos.setdefault(pid, []).append(d)
    out = {}
    for pid, dlist in by_pos.items():
        dlist.sort(key=lambda d: d.time)
        entry = next((d for d in dlist if getattr(d, "entry", 0) == mt5.DEAL_ENTRY_IN), dlist[0])
        exits = [d for d in dlist if getattr(d, "entry", 0) == mt5.DEAL_ENTRY_OUT]
        if not exits:
            continue
        pnl = round(sum(float(d.profit) for d in dlist), 2)
        out[pid] = {
            "position_id": pid,
            "comment": (entry.comment or "").strip(),
            "result": "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "BREAKEVEN"),
            "pnl": pnl,
            "close_price": float(exits[-1].price),
        }
    return out


def prefix_match(a, b):
    if not a or not b:
        return False
    return a == b or a.startswith(b) or b.startswith(a)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=["micro", "live"])
    ap.add_argument("--from", dest="from_dt", default=None, help="YYYY-MM-DD (default: 35 days ago)")
    ap.add_argument("--sheets", action="store_true", help="also compare the per-mode Sheets tab")
    args = ap.parse_args()

    magic = MAGIC_BY_MODE[args.mode]
    f = parse_dt(args.from_dt) if args.from_dt else datetime.now() - timedelta(days=35)

    db_path = db_for_mode(args.mode)
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    full = os.path.join(here, db_path)
    if not os.path.exists(full):
        print(f"No DB at {full} — nothing to verify."); return

    con = sqlite3.connect(full); con.row_factory = sqlite3.Row
    db_rows = con.execute(
        "SELECT trade_id, mt5_position_id, result, pnl_usd, close_price "
        "FROM trades WHERE result IN ('WIN','LOSS','BREAKEVEN')"
    ).fetchall()
    con.close()

    if not mt5.initialize():
        print("MT5 init failed:", mt5.last_error()); sys.exit(1)
    deals = mt5.history_deals_get(f - timedelta(hours=12), datetime.now() + timedelta(hours=12)) or []
    mt5_closed = group_closed_deals(deals, magic)
    mt5.shutdown()

    matched, mismatched, db_only = 0, [], []
    used_pids = set()
    for r in db_rows:
        m = None
        if r["mt5_position_id"] and r["mt5_position_id"] in mt5_closed:
            m = mt5_closed[r["mt5_position_id"]]
        else:
            for pid, d in mt5_closed.items():
                if prefix_match(r["trade_id"] or "", d["comment"]):
                    m = d; break
        if m is None:
            db_only.append(r["trade_id"]); continue
        used_pids.add(m["position_id"])
        ok = (r["result"] == m["result"]) and abs((r["pnl_usd"] or 0) - m["pnl"]) <= PNL_TOL
        if ok:
            matched += 1
        else:
            mismatched.append((r["trade_id"], f"db={r['result']}/{r['pnl_usd']}", f"mt5={m['result']}/{m['pnl']}"))

    mt5_only = [d["comment"] or f"pos{pid}" for pid, d in mt5_closed.items() if pid not in used_pids]

    print(f"\n=== Consistency: {args.mode} ({db_path} vs MT5 magic {magic}) ===")
    print(f"  DB closed rows : {len(db_rows)}")
    print(f"  MT5 closed pos : {len(mt5_closed)}")
    print(f"  ✓ matched      : {matched}")
    print(f"  ✗ mismatched   : {len(mismatched)}")
    for tid, a, b in mismatched[:20]:
        print(f"      {tid}: {a} | {b}")
    print(f"  ⚠ in DB only   : {len(db_only)}")
    for t in db_only[:20]:
        print(f"      {t}")
    print(f"  ⚠ in MT5 only  : {len(mt5_only)} (run import_mt5_history.py to capture)")
    for t in mt5_only[:20]:
        print(f"      {t}")

    if args.sheets:
        try:
            from agents.g4_sheets_logger import SheetsLogger
            sl = SheetsLogger(mode=args.mode)
            if sl.enabled and sl.trade_log_ws:
                rows = sl.trade_log_ws.get_all_values()
                print(f"  Sheets tab rows: {max(0, len(rows) - 1)} (header excluded)")
            else:
                print("  Sheets: disabled")
        except Exception as e:
            print(f"  Sheets check failed: {e}")

    verdict = "CLEAN ✓" if (not mismatched and not db_only) else "MISMATCH — review before reset"
    print(f"\n  Verdict: {verdict}\n")


if __name__ == "__main__":
    main()
