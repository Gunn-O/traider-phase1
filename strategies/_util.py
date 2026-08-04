"""
strategies/_util.py — shared pure helpers for the v2/v3 strategies

Ported verbatim from the validated snapshots' bt/strategies/_util.py
(reference/mai_ruay_v2_snapshot + reference/mountain_v3_snapshot — identical).
Shared by strategies/mai_ruay.py (MaiRuay v2) and strategies/mountain_v3_core.py
(Mountain v3) so both use ONE implementation — behaviour must match the snapshot
byte-for-byte.

*** pure functions only — no state, no strategy decision logic ***
Bars are duck-typed: any object with .open/.high/.low/.close (repo OHLC or the
snapshot's bt.contract.Bar) works, so the same helpers run in the live pipeline
AND inside the snapshot engine during parity.
"""
from __future__ import annotations

import math

PIP = 0.01          # 1 pip = 0.01 USD (XAUUSD) — matches bt.data.PIP
_MIN_LOT = 0.01     # lot floor (per leg: <0.01 → 0.01 · ≥0.01 → floor to 0.01)


def _r(x, n):
    return round(float(x), n)


# ---------- lot sizing per plan (risk = lot × SL distance) ----------
def _round_lot(x: float) -> float:
    """<0.01 → 0.01 (min); ≥0.01 → floor to 0.01 (with 1e-9 epsilon)."""
    if x < _MIN_LOT:
        return _MIN_LOT
    return math.floor(x * 100 + 1e-9) / 100


def _compute_lots(dists_pips, budget, split_mode):
    """lot per leg from budget (= portfolio×risk%). dists_pips = SL distance per
    leg (pip, >0).
      equal_risk : risk per leg = budget/N → lot_i = (budget/N)/dist_i
      equal_lot  : L = budget/Σdist → lot_i = L
    round per leg, then if Σ(lot_i×dist_i) > budget drop the LAST leg and
    recompute, down to 1 leg. returns list[lot] (len = kept legs)."""
    n = len(dists_pips)
    while n >= 1:
        sub = dists_pips[:n]
        if split_mode == "equal_lot":
            total = sum(sub)
            L = budget / total if total > 0 else _MIN_LOT
            raw = [L] * n
        else:   # equal_risk (default)
            per = budget / n
            raw = [(per / d if d > 0 else 0.0) for d in sub]
        lots = [_round_lot(x) for x in raw]
        total_risk = sum(l * d for l, d in zip(lots, sub))
        if total_risk <= budget or n == 1:
            return lots
        n -= 1   # over budget → drop last leg, recompute
    return []


# ---------- R55 (window size configurable — data.py's calc_r55 fixes 55) ----------
def _calc_r55(bars, end_idx: int, n: int) -> float:
    start = max(0, end_idx - n + 1)
    window = bars[start:end_idx + 1]
    if not window:
        return 0.0
    hi = max(b.high for b in window)
    lo = min(b.low for b in window)
    return (hi - lo) / PIP


# ---------- bar helpers ----------
def _body_pips(b) -> float: return abs(b.open - b.close) / PIP
def _is_bull(b) -> bool:    return b.close > b.open
def _is_bear(b) -> bool:    return b.close < b.open


# ---------- swing pairs (port of v4.45 scan_swings · reused across strategies) ----------
# Checks neighbours without crossing mid (left3+right2 · thick bar → left1+right1)
# + Doji extension + returns body_lo/body_hi. Used by Mountain v3.
def _swing_ok(window, li, rj, mid, kind, thick, right2_exc) -> bool:
    """Neighbours of the pair must not cross mid (high: O,C < mid all · low: O,C > mid).
      thick=True → check left1+right1 · normal left3+right2
      left neighbour off the left edge (k<0) → skip · right neighbour off the
      right edge (k≥n) → return right2_exc"""
    left  = [li - 1] if thick else [li - 3, li - 2, li - 1]
    right = [rj + 1] if thick else [rj + 1, rj + 2]
    n = len(window)
    for k in left:
        if k < 0:
            continue
        b = window[k]
        if (b.open >= mid or b.close >= mid) if kind == "high" else (b.open <= mid or b.close <= mid):
            return False
    for k in right:
        if k >= n:
            return right2_exc
        b = window[k]
        if (b.open >= mid or b.close >= mid) if kind == "high" else (b.open <= mid or b.close <= mid):
            return False
    return True


def scan_swings(window, r55, join_max_pip, min_body_pct_r55, thick_exc_pct_r55, start: int = 0):
    """Find all Swing High (Λ) / Low (V) pairs in window (port of v4.45).
      - join: |close_i − open_{i+1}| ≤ join_max_pip (pip)
      - each bar body ≥ min_body_pct_r55%×R55 (pip) · thick = body > thick_exc_pct_r55%×R55
      - mid = (close_i + open_{i+1})/2 · neighbours don't cross mid (_swing_ok)
      - Doji extension: a doji bar in the pair → extend to the next bar (L/R) · both doji → skip
      - right2 exception off (right2_exc=False) — v3 detects every bar
    returns (highs, lows) · each = {body_hi|body_lo, mid, bar=(i0+i1)/2, i0, i1, thick}"""
    min_body = min_body_pct_r55 / 100 * r55
    thick_th = thick_exc_pct_r55 / 100 * r55
    n = len(window)
    highs, lows = [], []
    seen_h, seen_l = set(), set()

    def _try(li, rj, kind):
        seen = seen_h if kind == "high" else seen_l
        if (li, rj) in seen:
            return
        b1, b2 = window[li], window[rj]
        if abs(b1.close - b2.open) / PIP > join_max_pip:
            return
        if _body_pips(b1) < min_body or _body_pips(b2) < min_body:
            return
        mid   = (b1.close + b2.open) / 2
        thick = _body_pips(b1) > thick_th or _body_pips(b2) > thick_th
        if not _swing_ok(window, li, rj, mid, kind, thick, right2_exc=False):
            return
        seen.add((li, rj))
        rec = {"mid": mid, "bar": (li + rj) / 2, "i0": li, "i1": rj, "thick": thick}
        if kind == "high":
            rec["body_hi"] = max(b1.open, b1.close, b2.open, b2.close)
            highs.append(rec)
        else:
            rec["body_lo"] = min(b1.open, b1.close, b2.open, b2.close)
            lows.append(rec)

    for i in range(max(0, start), n - 1):
        j = i + 1
        b1, b2 = window[i], window[j]
        if abs(b1.close - b2.open) / PIP > join_max_pip:   # adjacent pair too far → skip (parity v4.45)
            continue
        d1 = _body_pips(b1) < min_body
        d2 = _body_pips(b2) < min_body
        if not d1 and not d2:
            _try(i, j, "high"); _try(i, j, "low")
        elif not d1 and d2 and j + 1 < n:      # b2 doji → extend right
            _try(i, j + 1, "high"); _try(i, j + 1, "low")
        elif d1 and not d2 and i - 1 >= 0:      # b1 doji → extend left
            _try(i - 1, j, "high"); _try(i - 1, j, "low")
    return highs, lows
