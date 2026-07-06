#!/usr/bin/env python
# ============================================================================
# scripts/verify_mountain_v3_adapter.py — faithfulness check for the LIVE adapter
# ----------------------------------------------------------------------------
# GATE 2 proves the CORE is byte-identical in the snapshot engine. This proves
# the LIVE ADAPTER (strategies/mountain.py) reproduces the core's placements when
# driven the way the live pipeline drives it: a sliding window + cross-cycle
# state in mountain_state + live pending/position tags fed back each cycle.
#
# We replay the M1 data bar-by-bar, managing pendings/positions with the SNAPSHOT
# engine's OWN fill/exit rules (_check_limit_fill/_check_exit), calling the
# adapter each bar, and collecting every order it PLACES. Then we compare that
# set (tag → price/sl/tp) to golden = trades.csv ∪ unfilled.csv[reason≠min_tp]
# for BOTH configs. Identical placements ⇒ the adapter drives the core faithfully.
# ============================================================================
from __future__ import annotations

import csv
import os
import sys
from types import SimpleNamespace

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP = os.path.join(REPO_ROOT, "reference", "mountain_v3_snapshot")
DATA = os.path.join(SNAP, "data", "XAUUSD_M1_2026-06-09.csv")
sys.path.insert(0, SNAP)
sys.path.insert(0, REPO_ROOT)

from bt.data import load_csv                                  # noqa: E402
from bt.engine import _check_limit_fill, _check_exit          # noqa: E402
from strategies.mountain import find_signal, CONFIG_TPSL, CONFIG_RR85  # noqa: E402


def _golden_placed(expected_dir):
    """placements golden = filled trades ∪ unfilled that were actually placed
    (reason ≠ min_tp; min_tp legs are logged but never placed). key: tag."""
    placed = {}
    with open(os.path.join(expected_dir, "trades.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            placed[r["tag"]] = (round(float(r["entry"]), 3), round(float(r["sl"]), 3), round(float(r["tp"]), 3))
    with open(os.path.join(expected_dir, "unfilled.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["reason"] == "min_tp":
                continue
            placed[r["tag"]] = (round(float(r["limit_price"]), 3), round(float(r["sl"]), 3), round(float(r["tp"]), 3))
    return placed


# bounded live-style window (mimics CANDLES_LOOKBACK slide; also exercises the
# adapter's time-keyed state translation across shifting indices). ≥ r55(55) +
# F6 base→entry(42) + valid@C scan(54) margin.
LOOKBACK = 400


def _replay(bars, tf):
    """drive the adapter bar-by-bar; return {tag: (price,sl,tp)} of everything placed."""
    ms = {}
    pendings = {}    # tag -> order ns(price,sl,tp,lot,plan_id)
    positions = {}   # tag -> pos ns(direction,entry,sl,tp,lot,plan_id,tag)
    placed = {}
    for i, bar in enumerate(bars):
        win = bars[max(0, i - LOOKBACK + 1):i + 1]
        # (1) exit open positions (SL before TP — engine rule)
        for tag, pos in list(positions.items()):
            res, _ = _check_exit(pos, bar)
            if res:
                del positions[tag]
        # (2) fill pendings from prior bars
        for tag, o in list(pendings.items()):
            fp = _check_limit_fill(o, bar)
            if fp is not None:
                positions[tag] = SimpleNamespace(tag=tag, direction="BUY", entry=fp,
                                                 sl=o.sl, tp=o.tp, lot=o.lot, plan_id=o.plan_id)
                del pendings[tag]
        # (3) feed live state + drive the adapter
        ms["_live"] = {"pending_tags": list(pendings.keys()),
                       "position_plan_ids": [p.plan_id for p in positions.values()]}
        sig = find_signal(win, portfolio=1000.0, mountain_state=ms, tf=tf)
        # (4) apply cancels the core requested
        for tag in ms.get("_cancel", []):
            pendings.pop(tag, None)
        # (5) place new LIMITs; same-bar fill (5a) + child-bar exit (5b)
        if sig:
            for ep in sig.entries:
                o = SimpleNamespace(price=ep.price, sl=ep.sl, tp=ep.tp, lot=ep.lot,
                                    plan_id=ms.get("plan_id"))
                placed[ep.label] = (round(ep.price, 3), round(ep.sl, 3), round(ep.tp, 3))
                fp = _check_limit_fill(o, bar)
                if fp is not None:
                    pos = SimpleNamespace(tag=ep.label, direction="BUY", entry=fp,
                                          sl=o.sl, tp=o.tp, lot=o.lot, plan_id=o.plan_id)
                    res, _ = _check_exit(pos, bar)
                    if not res:
                        positions[ep.label] = pos
                else:
                    pendings[ep.label] = o
    return placed


def main() -> int:
    bars = load_csv(DATA)
    ok_all = True
    print("=" * 64)
    print("  Mountain v3 - LIVE ADAPTER faithfulness (placements vs golden)")
    print("=" * 64)
    for tf, exp in [("M1", "mountain_v3_tpsl"), ("M5", "mountain_v3_tpsl_rr85")]:
        golden = _golden_placed(os.path.join(SNAP, "expected_results", exp))
        got = _replay(bars, tf)
        missing = {t: golden[t] for t in golden if t not in got}
        extra = {t: got[t] for t in got if t not in golden}
        geom = {t: (golden[t], got[t]) for t in golden if t in got and golden[t] != got[t]}
        ok = not missing and not extra and not geom
        ok_all = ok_all and ok
        print(f"  [{tf} / {exp}]  {'MATCH' if ok else 'MISMATCH'}  "
              f"(golden {len(golden)} / adapter {len(got)})")
        for label, d in [("missing", missing), ("extra", extra), ("geom-diff", geom)]:
            if d:
                sample = list(d.items())[:4]
                print(f"      {label}: {len(d)}  e.g. {sample}")
    print("=" * 64)
    print("  RESULT: PASS" if ok_all else "  RESULT: FAIL")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
