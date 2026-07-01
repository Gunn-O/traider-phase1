"""
MAI_RUAY v2 — Father/Mother (clean, config-driven)

Source of truth = the validated snapshot engine
`reference/mai_ruay_v2_snapshot/bt/strategies/mai_ruay_v2.py` (`analyze_bar`) +
config `reference/.../configs/mairuay_v2_1entry_con360-510.yaml`.
Golden (snapshot engine, informational): 177 trades · WR 44.07% ·
net +24490.8 pip · portfolio 1000 → 8373.94.
Parity gate: `scripts/parity_mairuay_v2.py` (geometry per bar, lot at portfolio=1000).

This module ports the v2 STRATEGY LOGIC into the live pipeline's `Signal`/`EntryPoint`
contract (read by utils/signal_engine.py + main.py + broker/monitor). The snapshot's
own engine (proximity-cancel / pending expiry / one-plan guard) is NOT ported here —
those runtime behaviours are handled by the repo's position monitor / broker using
`details['pending_bars']` and `details['tp_cancel_buffer_pips']`.

What v2 DROPS vs the old V2.04 (not present here): Round 2 · lot ×2/÷2 ·
TP30-SL45 special · 3-entry split lot/3 · spread buffer · mother compared to %father
(v2 compares %R55). What v2 uses instead: config tiers · TP/SL = fixed % of father from
tech_point (per-leg adj) · proximity-cancel 5%R55 · min_tp 200 · pending 5 bars ·
lot = equal_risk from portfolio.

Geometry (mirrors analyze_bar):
  father_end = bar-2 · mother = bar-1 · child(entry) = bar
  father = single-colour run ending at father_end · mother = 1 opposite-colour pullback
  tech_point = (father_close + mother_open)/2 · TP/SL = fixed % of father size from tech
  entries = pick first tier whose when{father%, mother%} matches → legs → orders
"""
from __future__ import annotations

import math
import logging
from typing import List, Optional

from utils.xauusd_signal import OHLC, Signal, EntryPoint

logger = logging.getLogger(__name__)

PATTERN_NAME = "MAI_RUAY_M1"   # kept for pipeline/DB/Sheets continuity (one MaiRuay = v2)

# ─── Constants (mirror bt/data.py) ─────────────────────────────────
PIP           = 0.01     # 1 pip = 0.01 USD (XAUUSD)
RANGE_WINDOW  = 55       # R55 lookback
PENDING_BARS  = 5        # LIMIT pending expiry (bars) — = general.pending_max_age
_MIN_LOT      = 0.01     # per-leg lot floor

# ─── Config (must match mairuay_v2_1entry_con360-510.yaml exactly) ─
# *_pct values are percentages (divided by 100 when used as multipliers).
CONFIG = {
    "general": {
        "r55_bars": 55,
        "min_tp_pip": 200,
        "pending_max_age": 5,
        "proximity_cancel_enabled": True,
        "proximity_cancel_pct_r55": 5,
        "portfolio_start": 1000,        # default budget base; live overrides via portfolio arg
        "risk_per_plan_pct": 10,
        "lot_split_mode": "equal_risk",
    },
    "father": {
        "count_min": 1,
        "count_max": 10,
        "body_min_pct_r55": 60,
        "body_max_pct_r55": 0,          # 0 = unlimited
        "per_bar_body_min": 4,
        "vol_ratio_min": 1.0,
        "vol_window": 20,
        "doji_stop_pct": 2,
        "big_bar_pct": 10,
        "small_bar_allow": 2,
        "head_trim_small_max": 2,
    },
    "mother": {
        "compare_mode": "r55",
        "body_min_pct": 2,
        "body_max_pct": 25,
    },
    "entries": [
        {"when": {"father_min_pct": 80, "mother_min_pct": 2, "mother_max_pct": 25},
         "legs": [{"mode": "mother_pct", "value": 0, "adj_on": True, "tp_adj": 20}]},
        {"when": {"father_min_pct": 60, "mother_min_pct": 2, "mother_max_pct": 5},
         "legs": [{"mode": "mother_pct", "value": 0}]},
        {"when": {"father_min_pct": 60, "mother_min_pct": 5, "mother_max_pct": 10},
         "legs": [{"mode": "mother_pct", "value": 0}]},
        {"when": {"father_min_pct": 60, "mother_min_pct": 10, "mother_max_pct": 15},
         "legs": [{"mode": "mother_pct", "value": 0}]},
        {"when": {"father_min_pct": 60, "mother_min_pct": 15, "mother_max_pct": 25},
         "legs": [{"mode": "mother_pct", "value": 0}]},
    ],
    "tpsl": {"tp_pct_father": 40, "sl_pct_father": 20},
}


def _r(x, n):
    return round(float(x), n)


# ─── lot sizing (mirror bt/strategies/mai_ruay_v2._round_lot / _compute_lots) ──
def _round_lot(x: float) -> float:
    """<0.01 → 0.01 (min); ≥0.01 → floor to 0.01."""
    if x < _MIN_LOT:
        return _MIN_LOT
    return math.floor(x * 100 + 1e-9) / 100


def _compute_lots(dists_pips, budget, split_mode):
    """lot per leg from budget (= portfolio×risk%). dists_pips = SL distance per leg (pip, >0).
      equal_risk : risk per leg = budget/N → lot_i = (budget/N)/dist_i
      equal_lot  : L = budget/Σdist → lot_i = L
    round per leg, then if Σ(lot_i×dist_i) > budget drop the LAST leg and recompute,
    down to 1 leg. returns list[lot] (len = kept legs)."""
    n = len(dists_pips)
    while n >= 1:
        sub = dists_pips[:n]
        if split_mode == "equal_lot":
            total = sum(sub)
            L = budget / total if total > 0 else _MIN_LOT
            raw = [L] * n
        else:  # equal_risk
            per = budget / n
            raw = [(per / d if d > 0 else 0.0) for d in sub]
        lots = [_round_lot(x) for x in raw]
        total_risk = sum(l * d for l, d in zip(lots, sub))
        if total_risk <= budget or n == 1:
            return lots
        n -= 1
    return []


# ─── R55 + bar helpers (mirror mai_ruay_v2) ────────────────────────
def _calc_r55(bars: List[OHLC], end_idx: int, n: int = RANGE_WINDOW) -> float:
    start = max(0, end_idx - n + 1)
    window = bars[start:end_idx + 1]
    if not window:
        return 0.0
    hi = max(b.high for b in window)
    lo = min(b.low for b in window)
    return (hi - lo) / PIP


def _body_pips(b: OHLC) -> float: return abs(b.open - b.close) / PIP
def _is_bull(b: OHLC) -> bool:    return b.close > b.open
def _is_bear(b: OHLC) -> bool:    return b.close < b.open


# ─── father (mirror _find_father) ──────────────────────────────────
def _find_father(bars, father_end, r55, fc):
    """father = single-colour run ending at father_end. returns
    (start, end, dir, body_pips, vol_ratio) or None."""
    n = len(bars)
    if father_end < 0 or father_end >= n:
        return None
    eb = bars[father_end]
    if _is_bull(eb):
        run_dir = "UP"
    elif _is_bear(eb):
        run_dir = "DOWN"
    else:
        return None

    # bar after father must be the opposite-colour pullback (= mother slot)
    if father_end + 1 < n:
        nb = bars[father_end + 1]
        if (run_dir == "UP" and not _is_bear(nb)) or \
           (run_dir == "DOWN" and not _is_bull(nb)):
            return None

    doji    = fc["doji_stop_pct"] / 100
    per_bar = fc["per_bar_body_min"] / 100
    big     = fc["big_bar_pct"] / 100

    run_start = father_end
    for k in range(father_end - 1, max(-1, father_end - fc["count_max"]), -1):
        b = bars[k]
        same = (run_dir == "UP" and _is_bull(b)) or (run_dir == "DOWN" and _is_bear(b))
        if same and _body_pips(b) > r55 * doji:
            run_start = k
        else:
            break

    # trim small (body ≤ per_bar) head bars, up to head_trim_small_max
    trimmed = 0
    while run_start < father_end and trimmed < fc["head_trim_small_max"] \
            and _body_pips(bars[run_start]) <= r55 * per_bar:
        run_start += 1
        trimmed += 1

    length = father_end - run_start + 1
    if length < fc["count_min"]:
        return None

    seg = bars[run_start:father_end + 1]
    tb  = abs(seg[0].open - seg[-1].close) / PIP
    pct = tb / r55 * 100 if r55 > 0 else 0
    if pct < fc["body_min_pct_r55"]:
        return None
    bmax = fc.get("body_max_pct_r55", 0)
    if bmax and pct > bmax:
        return None

    # per-bar body: allow small (not doji) bars when big bars are the majority
    big_count = sum(1 for b in seg if _body_pips(b) > r55 * big)
    big_majority = big_count > length / 2
    fail = 0
    for b in seg:
        bp = _body_pips(b)
        if bp <= r55 * per_bar:
            if big_majority and bp > r55 * doji:
                fail += 1
            else:
                return None
    if fail > fc["small_bar_allow"]:
        return None

    # vol ratio: father avg body ÷ avg body of prior vol_window bars ≥ vol_ratio_min
    avg_body = tb / length
    pre = bars[max(0, run_start - fc["vol_window"]):run_start]
    vol_ratio = 0.0
    if pre:
        pre_avg = sum(_body_pips(b) for b in pre) / len(pre)
        vol_ratio = avg_body / pre_avg if pre_avg > 0 else 0.0
    if vol_ratio < fc["vol_ratio_min"]:
        return None

    return (run_start, father_end, run_dir, tb, _r(vol_ratio, 2))


# ─── mother (mirror _validate_mother) ──────────────────────────────
def _validate_mother(bars, mother_idx, f_dir, r55, f_body, mc):
    """returns (m_body_pips, m_pct) or None. m_pct vs compare_mode (r55|father)."""
    if mother_idx >= len(bars):
        return None
    m = bars[mother_idx]
    if f_dir == "UP" and not _is_bear(m):
        return None
    if f_dir == "DOWN" and not _is_bull(m):
        return None
    m_body = _body_pips(m)
    base = f_body if mc.get("compare_mode") == "father" else r55
    pct = m_body / base * 100 if base > 0 else 0
    if pct < mc["body_min_pct"] or pct > mc["body_max_pct"]:
        return None
    return (m_body, pct)


# ─── tier select (mirror _select_tier) ─────────────────────────────
def _select_tier(entries, f_pct, m_pct):
    """first tier where father ≥ father_min_pct and mother_min ≤ mother ≤ mother_max."""
    for tier in entries:
        w = tier.get("when", {})
        if f_pct >= w.get("father_min_pct", 0) \
                and w.get("mother_min_pct", 0) <= m_pct <= w.get("mother_max_pct", 1e9):
            return tier
    return None


# ─── core analyzer (mirror analyze_bar) ────────────────────────────
def _analyze_bar(bars: List[OHLC], bar_idx: int, portfolio: float = 1000.0,
                 debug: Optional[dict] = None) -> Optional[Signal]:
    def _skip(msg):
        if debug is not None:
            debug["skip"] = msg
        return None

    cfg = CONFIG
    g = cfg["general"]
    rw = g["r55_bars"]
    if bar_idx < rw - 1:
        return _skip(f"bar_idx {bar_idx} < {rw - 1}")
    mother_idx = bar_idx - 1
    father_end = bar_idx - 2
    if father_end < 0:
        return _skip("father_end < 0")

    r55 = _calc_r55(bars, bar_idx - 1, rw)          # R55 at end of mother bar
    if r55 <= 0:
        return _skip("r55 <= 0")

    fr = _find_father(bars, father_end, r55, cfg["father"])
    if fr is None:
        return _skip("father fail")
    f_start, f_end, f_dir, f_body, vol_ratio = fr
    f_pct = f_body / r55 * 100 if r55 > 0 else 0

    mc = cfg["mother"]
    mr = _validate_mother(bars, mother_idx, f_dir, r55, f_body, mc)
    if mr is None:
        return _skip("mother fail")
    m_body, m_pct = mr

    tier = _select_tier(cfg["entries"], f_pct, m_pct)
    if tier is None:
        return _skip(f"no tier (father {f_pct:.1f}%, mother {m_pct:.1f}%)")

    mai_dir      = "BUY" if f_dir == "DOWN" else "SELL"
    father_close = bars[f_end].close
    m_row        = bars[mother_idx]
    mother_open  = m_row.open
    tech_point   = (father_close + mother_open) / 2
    mother_body_len = abs(mother_open - m_row.close)
    child        = bars[bar_idx]

    # base TP/SL = fixed % of father size, measured from tech_point
    tp_off = f_body * (cfg["tpsl"]["tp_pct_father"] / 100) * PIP
    sl_off = f_body * (cfg["tpsl"]["sl_pct_father"] / 100) * PIP
    sl     = tech_point - sl_off if mai_dir == "BUY" else tech_point + sl_off
    tp_sel = tech_point + tp_off if mai_dir == "BUY" else tech_point - tp_off

    sign     = 1 if mai_dir == "BUY" else -1
    min_tp   = g["min_tp_pip"]
    tp_pct_b = cfg["tpsl"]["tp_pct_father"]
    sl_pct_b = cfg["tpsl"]["sl_pct_father"]

    legs = []   # (ep, label, is_market, sl_i, tp_i)
    for idx, leg in enumerate(tier["legs"]):
        if leg["mode"] == "market":
            ep, label, mkt = child.open, f"ไม้{idx + 1}:market", True
        else:  # mother_pct — LIMIT at tech ± mother_body_len·value/100 (mirror BUY/SELL)
            val = leg["value"]
            ep = tech_point + sign * mother_body_len * (val / 100)
            label, mkt = f"ไม้{idx + 1}:แม่{val:g}%", False
        # per-leg TP/SL adjust (units = % of father, same base). adj_on≠False and adj≠0 → base+adj
        use = (leg.get("adj_on") is not False)
        tp_pct_i = tp_pct_b + (leg.get("tp_adj") or 0 if use else 0)
        sl_pct_i = sl_pct_b + (leg.get("sl_adj") or 0 if use else 0)
        if sl_pct_i <= 0:
            sl_pct_i = sl_pct_b
        if tp_pct_i == tp_pct_b and sl_pct_i == sl_pct_b:
            sl_i, tp_i = sl, tp_sel
        else:
            tp_off_i = f_body * (tp_pct_i / 100) * PIP
            sl_off_i = f_body * (sl_pct_i / 100) * PIP
            sl_i = tech_point - sl_off_i if mai_dir == "BUY" else tech_point + sl_off_i
            tp_i = tech_point + tp_off_i if mai_dir == "BUY" else tech_point - tp_off_i
        tp_dist = ((tp_i - ep) if mai_dir == "BUY" else (ep - tp_i)) / PIP
        if tp_dist < min_tp:
            continue   # TP too close / wrong side of entry → drop this leg
        legs.append((ep, label, mkt, sl_i, tp_i))

    if not legs:
        return _skip("all legs dropped (min_tp)")

    # lot per leg: budget = portfolio × risk% (live passes real balance; parity passes 1000)
    first_price = legs[0][0]
    sl_pips = abs(first_price - sl) / PIP
    if sl_pips <= 0:
        return _skip("sl_pips <= 0")
    risk_pct   = g.get("risk_per_plan_pct", 10)
    split_mode = g.get("lot_split_mode", "equal_risk")
    budget = float(portfolio) * (risk_pct / 100)
    dists_pips = [abs(ep - sl_i) / PIP for ep, _, _, sl_i, _ in legs]
    lots = _compute_lots(dists_pips, budget, split_mode)
    if not lots:
        return _skip("no lots")
    kept = legs[:len(lots)]

    entries = [
        EntryPoint(price=ep, label=label, lot=_r(lots[k], 2),
                   is_market=mkt, tp=tp_i, sl=sl_i)
        for k, (ep, label, mkt, sl_i, tp_i) in enumerate(kept)
    ]
    lot = _r(sum(lots), 2)

    first = entries[0]
    entry     = first.price
    sl_price  = first.sl
    tp_price  = first.tp
    risk_pip  = abs(entry - sl_price) / PIP
    reward_pip = abs(tp_price - entry) / PIP
    rr = reward_pip / risk_pip if risk_pip > 0 else 0.0

    def _bar_num(i):
        return bars[i].bar_num if bars[i].bar_num else i + 1

    return Signal(
        pattern    = PATTERN_NAME,
        direction  = mai_dir,
        quality    = "✓",                       # Signal Engine confidence = 1.0 always
        entry      = entry,
        sl         = sl_price,
        sl_name    = "SL_MR_V2",
        tp_order   = tp_price,                  # v2 has no spread buffer
        tp_ref     = tp_price,
        tp_name    = f"TP {tp_pct_b}%พ่อ",
        rr         = rr,
        risk_pip   = risk_pip,
        reward_pip = reward_pip,
        lot        = lot,
        R55        = r55,
        # ── v2 multi-entry ──────────────────────────────
        entries     = entries,
        is_round2   = False,                    # v2 has no Round 2
        father_pass = f"father {f_pct:.1f}%R55 ({f_end - f_start + 1} bars) · vol {vol_ratio:.2f}",
        vol_ratio   = vol_ratio,
        details    = {
            "father_start": f_start, "father_end": f_end,
            "father_bars": f_end - f_start + 1,
            "father_body_pips": f_body, "father_pct_r55": f_pct,
            "mother_idx": mother_idx, "mother_body_pips": m_body,
            "mother_pct_r55": m_pct,
            "tech_point": tech_point,
            # first-entry order type for main.py / broker / monitor
            "order_type": "MARKET" if first.is_market else "LIMIT",
            # pending expiry (bars) = general.pending_max_age
            "pending_bars": g["pending_max_age"],
            # proximity-cancel buffer = proximity_cancel_pct_r55 (5%) × R55  (pip units)
            "tp_cancel_buffer_pips": r55 * (g["proximity_cancel_pct_r55"] / 100),
            "swing_bar_nums": {_bar_num(f_start), _bar_num(f_end), _bar_num(mother_idx)},
        },
    )


# ════════════════════════════════════════════════════════════════
# Public API — matches strategies signature used by signal_engine
# ════════════════════════════════════════════════════════════════
def find_signal(
    bars: List[OHLC],
    portfolio: float = 1000.0,
    round2_info: Optional[dict] = None,   # deprecated no-op (v2 has no Round 2) — removed in wiring cleanup
    debug: Optional[dict] = None,
) -> Optional[Signal]:
    """Analyse the last bar (bars[-1]) and return a MaiRuay v2 Signal, or None.

    round2_info is accepted for backward-compat only and is ignored — v2 has no
    Round 2. (The wiring that used to pass it is removed separately.)
    """
    if round2_info:
        logger.warning("mai_ruay.find_signal: round2_info ignored — MaiRuay v2 has no Round 2")

    if len(bars) < RANGE_WINDOW:
        if debug is not None:
            debug["skip"] = f"bars {len(bars)} < {RANGE_WINDOW}"
        return None

    for i, b in enumerate(bars):
        if b.bar_num == 0:
            b.bar_num = i + 1

    return _analyze_bar(bars, len(bars) - 1, portfolio=portfolio, debug=debug)
