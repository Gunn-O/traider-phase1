#!/usr/bin/env python
# ============================================================================
# scripts/parity_mairuay_v2.py — GEOMETRY PARITY GATE for MaiRuay v2 rewrite
# ----------------------------------------------------------------------------
# Compares, bar-by-bar, the signal GEOMETRY produced by:
#   REFERENCE : reference/mai_ruay_v2_snapshot/bt/strategies/mai_ruay_v2.analyze_bar
#               (the validated snapshot — golden 177/44.07%/+24490.8/->8373.94)
#   REPO      : strategies/mai_ruay.find_signal(window, portfolio=1000)
#
# Gate (per the approved plan):
#   - primary  : direction / kind / entry / sl / tp identical at EVERY bar
#                (price tolerance <= 0.005 = 3-dp round). balance-independent.
#   - lot      : compared ONLY at portfolio=1000 (v2 lot source = fixed
#                portfolio_start). tolerance <= 0.005.
#   exit 0 iff zero mismatches, zero repo-extra, zero repo-missing.
#
# NOTE: this is a strategy-correctness check (analyze_bar vs find_signal), NOT
#       an engine/sim reproduction. Byte-identical result files are out of scope.
# ============================================================================
from __future__ import annotations

import os
import sys

# ---- paths -----------------------------------------------------------------
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP = os.path.join(REPO_ROOT, "reference", "mai_ruay_v2_snapshot")
DATA = os.path.join(SNAP, "data", "XAUUSD_M1_2026-06-09.csv")
SCFG = os.path.join(SNAP, "configs", "mairuay_v2_1entry_con360-510.yaml")

# repo root first so `utils`/`strategies` resolve to the live repo;
# snapshot dir so `bt` (the reference engine) resolves.
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, SNAP)

import yaml  # noqa: E402

from bt.data import load_csv                       # reference loader  # noqa: E402
from bt.strategies import mai_ruay_v2 as ref       # reference strategy # noqa: E402

from utils.xauusd_signal import OHLC               # repo bar type      # noqa: E402
from strategies import mai_ruay as repo            # repo strategy      # noqa: E402

PORTFOLIO = 1000.0
PRICE_TOL = 0.005      # 3-dp round tolerance (report writes 3-dp prices)
LOT_TOL   = 0.005
LOOKBACK  = 160        # tail window for repo find_signal (> r55 55 + vol 20 + father 10)
MAX_SHOW  = 25         # first N mismatches to print


def _geom_ref(sig):
    """reference Signal.entries = list[(ep, label, lot, mkt, sl_i, tp_i)]."""
    if sig is None:
        return []
    out = []
    for ep, _label, lot, mkt, sl_i, tp_i in sig.entries:
        out.append((sig.direction, "MARKET" if mkt else "LIMIT",
                    round(ep, 3), round(sl_i, 3), round(tp_i, 3), round(lot, 2)))
    return out


def _geom_repo(sig):
    """repo Signal.entries = list[EntryPoint(price,label,lot,is_market,tp,sl)]."""
    if sig is None or not getattr(sig, "entries", None):
        return []
    out = []
    for e in sig.entries:
        out.append((sig.direction, "MARKET" if e.is_market else "LIMIT",
                    round(e.price, 3), round(e.sl, 3), round(e.tp, 3), round(e.lot, 2)))
    return out


def _rows_match(a, b):
    """compare one entry tuple within tolerance. returns (geom_ok, lot_ok)."""
    if a[0] != b[0] or a[1] != b[1]:
        return False, False
    geom_ok = (abs(a[2] - b[2]) <= PRICE_TOL and
               abs(a[3] - b[3]) <= PRICE_TOL and
               abs(a[4] - b[4]) <= PRICE_TOL)
    lot_ok = abs(a[5] - b[5]) <= LOT_TOL
    return geom_ok, lot_ok


def main() -> int:
    scfg = yaml.safe_load(open(SCFG, encoding="utf-8"))
    bars = load_csv(DATA)
    n = len(bars)

    # build repo OHLC list ONCE; preset bar_num so find_signal won't re-stamp
    repo_bars = [OHLC(time=str(b.time), open=b.open, high=b.high,
                      low=b.low, close=b.close, bar_num=i + 1)
                 for i, b in enumerate(bars)]

    ref_signals = 0          # bars where reference emitted >=1 order
    geom_mismatch = 0        # bars whose geometry differs
    lot_mismatch = 0         # bars whose geometry matches but lot differs
    repo_extra = 0           # repo emitted, reference did not
    repo_missing = 0         # reference emitted, repo did not
    matched = 0              # bars fully matching (geom + lot)
    errors = 0
    show = []

    for i in range(n):
        ref_g = _geom_ref(ref.analyze_bar(bars, i, scfg))
        if ref_g:
            ref_signals += 1

        try:
            lo = max(0, i - LOOKBACK + 1)
            repo_sig = repo.find_signal(repo_bars[lo:i + 1], portfolio=PORTFOLIO)
            repo_g = _geom_repo(repo_sig)
        except Exception as exc:  # noqa: BLE001
            errors += 1
            if len(show) < MAX_SHOW:
                show.append((i, f"repo raised {type(exc).__name__}: {exc}"))
            if ref_g:
                repo_missing += 1
            continue

        if not ref_g and not repo_g:
            continue
        if ref_g and not repo_g:
            repo_missing += 1
            if len(show) < MAX_SHOW:
                show.append((i, f"ref={ref_g} repo=None"))
            continue
        if repo_g and not ref_g:
            repo_extra += 1
            if len(show) < MAX_SHOW:
                show.append((i, f"ref=None repo={repo_g}"))
            continue

        # both non-empty
        if len(ref_g) != len(repo_g):
            geom_mismatch += 1
            if len(show) < MAX_SHOW:
                show.append((i, f"len {len(ref_g)}!={len(repo_g)} ref={ref_g} repo={repo_g}"))
            continue
        g_ok = l_ok = True
        for a, b in zip(ref_g, repo_g):
            go, lo_ok = _rows_match(a, b)
            g_ok = g_ok and go
            l_ok = l_ok and lo_ok
        if not g_ok:
            geom_mismatch += 1
            if len(show) < MAX_SHOW:
                show.append((i, f"GEOM ref={ref_g} repo={repo_g}"))
        elif not l_ok:
            lot_mismatch += 1
            if len(show) < MAX_SHOW:
                show.append((i, f"LOT  ref={ref_g} repo={repo_g}"))
        else:
            matched += 1

    ok = (geom_mismatch == 0 and lot_mismatch == 0 and
          repo_extra == 0 and repo_missing == 0 and errors == 0)

    print("=" * 64)
    print("  MaiRuay v2 — GEOMETRY PARITY  (analyze_bar[ref] vs find_signal[repo])")
    print("=" * 64)
    print(f"  bars scanned        : {n}")
    print(f"  reference signals   : {ref_signals}")
    print(f"  fully matched       : {matched}")
    print(f"  geometry mismatch   : {geom_mismatch}")
    print(f"  lot mismatch        : {lot_mismatch}")
    print(f"  repo extra (ref=∅)  : {repo_extra}")
    print(f"  repo missing (repo=∅): {repo_missing}")
    print(f"  repo exceptions     : {errors}")
    if show:
        print("-" * 64)
        print(f"  first {len(show)} discrepancies:")
        for idx, msg in show:
            print(f"    bar {idx}: {msg}")
    print("=" * 64)
    print("  golden (engine, informational): 177 trades · WR 44.07% · "
          "net +24490.8 pip · port 1000 -> 8373.94")
    print("=" * 64)
    if ok:
        print("  RESULT: PASS  (geometry identical every bar; lot matches at portfolio=1000)")
        return 0
    print("  RESULT: FAIL  (see discrepancies above)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
