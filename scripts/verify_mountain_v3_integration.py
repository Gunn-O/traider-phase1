#!/usr/bin/env python
# ============================================================================
# scripts/verify_mountain_v3_integration.py — Phase 3b integration check
# ----------------------------------------------------------------------------
# Validates the LIVE wiring (signal_engine MOUNTAIN block + main.py _live/_cancel
# routing) end-to-end, NOT just the adapter. It drives the real run_signal_engine
# and replicates main.py's run_once order-lifecycle around it:
#   - manage a mock position_monitor.open_orders (fill pendings / exit positions
#     with the snapshot engine's own rules),
#   - populate mountain_state['_live'] EXACTLY like main.py (from open_orders),
#   - call run_signal_engine (Mountain active),
#   - route mountain_state['_cancel'] EXACTLY like main.py (mark CANCELLED),
#   - add placed Signal.entries as PENDING Mountain orders.
# Then compare every placement to golden and assert cancels were applied.
#
# Runs a prefix (fast) with a bounded live-style window. PASS ⇒ the signal_engine
# wiring + _live feed + _cancel routing reproduce the validated placements and the
# core's cancels flow through the main.py path.
# ============================================================================
from __future__ import annotations

import csv
import os
import sys
from types import SimpleNamespace

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP = os.path.join(REPO_ROOT, "reference", "mountain_v3_snapshot")
sys.path.insert(0, SNAP)
sys.path.insert(0, REPO_ROOT)

os.environ["TRAIDER_BACKTEST_ACTIVE"] = "1"   # backtest mode → no forming-bar drop
os.environ["BACKTEST_TIMEFRAME"] = "M1"

from datetime import timezone                                   # noqa: E402
from bt.data import load_csv                                    # noqa: E402
from bt.engine import _check_limit_fill, _check_exit            # noqa: E402
import utils.strategy_loader as _sl                             # noqa: E402
_sl.is_pattern_active_for_tf = lambda p, tf: p == "MOUNTAIN"    # activate Mountain only
import utils.signal_engine as se                                # noqa: E402
# Disable the repo's Friday-close/gap guards for this WIRING test — the snapshot
# golden ignores them (the core doesn't read allow_new_entry), so leaving them on
# would make run_signal_engine skip the adapter on guard bars and diverge BY
# DESIGN. Disabling isolates "does the wiring faithfully drive the core?".
se.is_near_market_close = lambda *a, **k: False
if hasattr(se, "check_opening_gap"):
    se.check_opening_gap = lambda *a, **k: False

N = 15000        # prefix bars (contains the first ~20 plans + cancels)
LOOKBACK = 400   # bounded live-style window


def _candle(b):
    return {"timestamp": b.time.to_pydatetime().replace(tzinfo=timezone.utc),
            "open": b.open, "high": b.high, "low": b.low, "close": b.close,
            "volume": b.volume or 1}


def _core_pid(label):
    try:
        return int(str(label).split("#", 1)[1].split(":", 1)[0])
    except (IndexError, ValueError):
        return None


def main() -> int:
    bars = load_csv(os.path.join(SNAP, "data", "XAUUSD_M1_2026-06-09.csv"))
    gold = {}
    with open(os.path.join(SNAP, "expected_results/mountain_v3_tpsl/trades.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if int(r["entry_bar"]) < N:
                gold[r["tag"]] = (round(float(r["entry"]), 3), round(float(r["sl"]), 3), round(float(r["tp"]), 3))
    with open(os.path.join(SNAP, "expected_results/mountain_v3_tpsl/unfilled.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["reason"] != "min_tp" and int(r["place_bar"]) < N:
                gold[r["tag"]] = (round(float(r["limit_price"]), 3), round(float(r["sl"]), 3), round(float(r["tp"]), 3))

    ms = {}
    open_orders = []      # mock position_monitor.open_orders (dicts like main.py)
    placed = {}
    cancels_applied = 0

    candles_all = [_candle(b) for b in bars]

    for i in range(N):
        bar = bars[i]
        lo = max(0, i - LOOKBACK + 1)
        win_candles = candles_all[lo:i + 1]

        # (Step 0) exit positions + fill pendings (engine rules), mirror main.py monitor
        for o in open_orders:
            if o["result"] != "PENDING":
                continue
            od = SimpleNamespace(price=o["entry_price"], sl=o["sl_price"], tp=o["tp_price"], lot=o["lot"])
            if o.get("filled"):
                pos = SimpleNamespace(direction="BUY", entry=o["entry_price"], sl=o["sl_price"], tp=o["tp_price"])
                res, _ = _check_exit(pos, bar)
                if res:
                    o["result"] = res
            else:
                fp = _check_limit_fill(od, bar)
                if fp is not None:
                    o["filled"] = True
                    o["entry_price"] = fp
        open_orders = [o for o in open_orders if o["result"] == "PENDING"]

        # (main.py before run_signal_engine) populate mountain_state['_live']
        if not isinstance(ms, dict):
            ms = {}
        _pend, _pos = [], []
        for o in open_orders:
            if o["pattern"] != "MOUNTAIN" or o["result"] != "PENDING":
                continue
            if o.get("filled"):
                pid = _core_pid(o.get("entry_label"))
                if pid is not None:
                    _pos.append(pid)
            elif o.get("entry_label"):
                _pend.append(o["entry_label"])
        ms["_live"] = {"pending_tags": _pend, "position_plan_ids": _pos}

        ws = se.run_signal_engine(candles_by_tf={"M1": win_candles}, portfolio=1000.0, mountain_state=ms)

        # (main.py after run_signal_engine) route _cancel
        mtn_cancel = list((ms or {}).get("_cancel") or []) if isinstance(ms, dict) else []
        ms = ws.get("mountain_state") or {}
        if mtn_cancel:
            for o in open_orders:
                if (o.get("entry_label") in mtn_cancel and o["pattern"] == "MOUNTAIN"
                        and o["result"] == "PENDING" and not o.get("filled")):
                    o["result"] = "CANCELLED"
                    cancels_applied += 1
            open_orders = [o for o in open_orders if o["result"] == "PENDING"]

        # (main.py) place new Signal.entries as PENDING Mountain orders. To make
        # the lifecycle match the validated snapshot engine (so we can compare to
        # golden and prove the run_signal_engine + _live/_cancel WIRING is
        # transparent), apply same-bar fill (engine step 5a) + child-bar exit (5b).
        sig = ws.get("signal")
        if sig and sig.pattern == "MOUNTAIN":
            for ep in sig.entries:
                placed[ep.label] = (round(ep.price, 3), round(ep.sl, 3), round(ep.tp, 3))
                o = {"entry_label": ep.label, "pattern": "MOUNTAIN", "order_type": "LIMIT",
                     "result": "PENDING", "filled": False,
                     "entry_price": ep.price, "sl_price": ep.sl, "tp_price": ep.tp, "lot": ep.lot}
                od = SimpleNamespace(price=ep.price, sl=ep.sl, tp=ep.tp, lot=ep.lot)
                fp = _check_limit_fill(od, bar)      # same-bar fill (5a)
                if fp is not None:
                    o["filled"] = True
                    o["entry_price"] = fp
                    pos = SimpleNamespace(direction="BUY", entry=fp, sl=ep.sl, tp=ep.tp)
                    res, _ = _check_exit(pos, bar)   # child-bar exit (5b)
                    if res:
                        o["result"] = res
                if o["result"] == "PENDING":
                    open_orders.append(o)

    miss = {t: gold[t] for t in gold if t not in placed}
    extra = {t: placed[t] for t in placed if t not in gold}
    geom = {t: (gold[t], placed[t]) for t in gold if t in placed and gold[t] != placed[t]}
    ok = not miss and not extra and not geom and cancels_applied > 0

    print("=" * 64)
    print(f"  Mountain v3 INTEGRATION (signal_engine + main.py _live/_cancel), prefix N={N}")
    print("=" * 64)
    print(f"  golden placements   : {len(gold)}")
    print(f"  integration placed  : {len(placed)}")
    print(f"  missing/extra/geom  : {len(miss)}/{len(extra)}/{len(geom)}")
    print(f"  CANCEL_MOUNTAIN applied via main.py routing: {cancels_applied}")
    for label, d in [("missing", miss), ("extra", extra), ("geom", geom)]:
        if d:
            print(f"    {label}: {list(d.items())[:3]}")
    print("=" * 64)
    print("  RESULT: PASS" if ok else "  RESULT: FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
