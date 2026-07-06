"""
strategies/mountain.py — Mountain v3 LIVE adapter (contract-preserving)

Drives the validated strategies/mountain_v3_core.MountainV3 core on the live
sliding window and returns the repo Signal contract. The core is stateful and
uses absolute bar indices (it was validated by the snapshot engine replaying from
bar 0); the live pipeline passes a bounded, sliding window each cycle. This
adapter bridges the two WITHOUT forking the core's logic:

  • each cycle we build a Context from the current window + the live Mountain
    pending/position tags (supplied by main.py via mountain_state['_live']);
  • cross-cycle core state (_used / _used_peaks / _armed / _plan_id) is persisted
    in mountain_state keyed by bar TIME (not index) so it survives the window
    sliding — a bar index `v = (i0+i1)/2` round-trips through the times of bars
    floor(v)/ceil(v), which reconstructs the exact same v in any shifted frame;
  • we call the real core.on_bar(ctx) once per new closed bar and translate its
    Decision → Signal.entries (place) / mountain_state['_cancel'] (cancel).

Config is per-TF (spec): M1 → tpsl (R:R 1.0) · M5 → rr85 (R:R 0.85). Values match
reference/mountain_v3_snapshot/configs/*.yaml exactly. lot budget uses the live
`portfolio` (injected into cfg['portfolio_start']); parity passes 1000.

Pattern id stays 'MOUNTAIN' (pipeline/DB/Sheets continuity). Mountain v3 has NO
trailing — closes at fixed %height SL/TP only.
"""
from __future__ import annotations

import copy
import logging
import math
from types import SimpleNamespace
from typing import List, Optional

from utils.xauusd_signal import OHLC, Signal, EntryPoint
from strategies._util import PIP, _calc_r55
from strategies.mountain_v3_core import MountainV3

logger = logging.getLogger(__name__)

PATTERN_NAME = "MOUNTAIN"

# ── configs (match reference/mountain_v3_snapshot/configs/*.yaml exactly) ──
_BASE_CFG = {
    "r55_bars": 55,
    "portfolio_start": 1000, "risk_per_plan_pct": 10,
    "pair_join_max_pip": 50, "pair_min_body_pct_r55": 1, "thick_exc_pct_r55": 10,
    "min_height_pct_r55": 50, "min_mountain_bars": 10, "max_base_to_entry_bars": 42,
    "peak_lock_pct": 10,
    "upleg_check_min_bars": 10, "upleg_max_count": 2,
    "downleg_check_min_bars": 10, "downleg_max_count": 2,
    "pending_expiry_bars": 5,
    "tp_pct_height": 40, "sl_pct_height": 35, "min_tp_pip": 200,
}
# M1: tp_adj +5 → TP 45%/SL 35% → R:R 1.0
CONFIG_TPSL = {**_BASE_CFG, "entries": [
    {"when": {"height_min_pct_r55": 50}, "legs": [{"offset_pct_height": 5, "tp_adj": 5}]}]}
# M5: adj_on false → base TP 40%/SL 35% → R:R 0.85
CONFIG_RR85 = {**_BASE_CFG, "entries": [
    {"when": {"height_min_pct_r55": 50}, "legs": [{"offset_pct_height": 5, "adj_on": False}]}]}


def _config_for_tf(tf: Optional[str]) -> dict:
    """M1 → tpsl (R:R 1.0) · everything else (M5 deploy) → rr85 (R:R 0.85)."""
    return CONFIG_TPSL if (tf or "M1").upper() == "M1" else CONFIG_RR85


# ── bar-index ↔ time round-trip (survives the window sliding) ──
def _barval_to_pair(v: float, bars: List[OHLC]):
    """index v=(i0+i1)/2 → (time[floor v], time[ceil v]); those two bars
    reconstruct v exactly in any shifted frame (indices shift uniformly)."""
    lo, hi = int(math.floor(v)), int(math.ceil(v))
    if 0 <= lo < len(bars) and 0 <= hi < len(bars):
        return [str(bars[lo].time), str(bars[hi].time)]
    return None


def _pair_to_barval(pair, t2i) -> Optional[float]:
    if not pair:
        return None
    lo, hi = t2i.get(pair[0]), t2i.get(pair[1])
    if lo is None or hi is None:
        return None
    return (lo + hi) / 2


def _restore_core(core: MountainV3, ms: dict, bars: List[OHLC], t2i: dict) -> None:
    """rebuild core cross-cycle state from mountain_state (index frame = current window)."""
    core._plan_id = int(ms.get("plan_id", 0))
    core._used = {v for v in (_pair_to_barval(p, t2i) for p in ms.get("used_bases", [])) if v is not None}
    core._used_peaks = {v for v in (_pair_to_barval(p, t2i) for p in ms.get("used_peaks", [])) if v is not None}
    # F8 is FIRST-SEEN (computed once at the bar a base is first detected, with
    # that bar's i) → must persist the verdict, else recomputing with a growing
    # range each cycle can flip valid↔rejected and desync from the engine.
    core._base_check = {}
    for pair, verdict in ms.get("base_check", []):
        v = _pair_to_barval(pair, t2i)
        if v is not None:
            core._base_check[v] = verdict
    armed = ms.get("armed")
    core._armed, core._pend = None, {}
    if armed:
        base_bar = _pair_to_barval(armed.get("base_pair"), t2i)
        legs, pend = [], {}
        for lg in armed.get("legs", []):
            pidx = t2i.get(lg.get("place_time"))
            if pidx is None:   # placed bar slid out of the window → treat leg as gone
                continue
            legs.append({"tag": lg["tag"], "place_bar": pidx})
            pend[lg["tag"]] = {"plan_id": armed["plan_id"], "price": lg.get("price"),
                               "placed": pidx, "sl": lg.get("sl"), "tp_sel": lg.get("tp"),
                               "dir": "BUY", "place_time": lg.get("place_time")}
        if base_bar is not None and legs:
            core._armed = {"plan_id": armed["plan_id"], "base_bar": base_bar,
                           "base_lo": armed["base_lo"],
                           "peak_bar": _pair_to_barval(armed.get("peak_pair"), t2i),
                           "peak_hi": armed["peak_hi"], "height": armed["height"], "legs": legs}
            core._pend = pend


def _extract_core(core: MountainV3, bars: List[OHLC]) -> dict:
    """serialise core cross-cycle state → mountain_state (time-keyed)."""
    out = {"plan_id": core._plan_id,
           "used_bases": [p for p in (_barval_to_pair(v, bars) for v in core._used) if p],
           "used_peaks": [p for p in (_barval_to_pair(v, bars) for v in core._used_peaks) if p],
           "base_check": [[_barval_to_pair(v, bars), verdict]
                          for v, verdict in core._base_check.items()
                          if _barval_to_pair(v, bars) is not None]}
    a = core._armed
    if a:
        legs = []
        for lg in a["legs"]:
            m = core._pend.get(lg["tag"], {})
            pb = lg["place_bar"]
            place_time = str(bars[pb].time) if 0 <= pb < len(bars) else m.get("place_time")
            legs.append({"tag": lg["tag"], "place_time": place_time,
                         "price": m.get("price"), "sl": m.get("sl"), "tp": m.get("tp_sel")})
        out["armed"] = {"plan_id": a["plan_id"], "base_pair": _barval_to_pair(a["base_bar"], bars),
                        "base_lo": a["base_lo"], "peak_pair": _barval_to_pair(a["peak_bar"], bars) if a.get("peak_bar") is not None else None,
                        "peak_hi": a["peak_hi"], "height": a["height"], "legs": legs}
    else:
        out["armed"] = None
    return out


def find_signal(
    bars: List[OHLC],
    portfolio: float = 1000.0,
    mountain_state: Optional[dict] = None,
    debug: Optional[dict] = None,
    tf: Optional[str] = "M1",
) -> Optional[Signal]:
    """Drive Mountain v3 core for the current bar. Returns a Signal when a plan is
    placed, else None. Reads/writes cross-cycle state in `mountain_state` (mutated
    in place): persists core state, and sets mountain_state['_cancel'] = [tags] for
    the pending orders the core wants cancelled this cycle (main.py routes them)."""
    if mountain_state is None:
        mountain_state = {}
    mountain_state["_cancel"] = []          # reset per cycle
    if len(bars) < 2:
        if debug is not None:
            debug["skip"] = f"bars {len(bars)} < 2"
        return None

    # process each closed bar once (guard against multiple cycles on the same bar)
    cur_time = str(bars[-1].time)
    if mountain_state.get("last_bar_time") == cur_time:
        if debug is not None:
            debug["skip"] = "bar already processed this close"
        return None

    cfg = dict(_config_for_tf(tf))
    cfg["portfolio_start"] = float(portfolio)   # live lot budget base (parity passes 1000)

    t2i = {str(b.time): k for k, b in enumerate(bars)}
    live = mountain_state.get("_live") or {}
    ctx = SimpleNamespace(
        bar=bars[-1], bar_index=len(bars) - 1, window=bars,
        positions=[SimpleNamespace(tag="", plan_id=pid) for pid in live.get("position_plan_ids", [])],
        pendings=[SimpleNamespace(tag=t) for t in live.get("pending_tags", [])],
        last_closed=[], allow_new_entry=True,   # core reads neither
    )

    core = MountainV3(cfg, portfolio=float(portfolio))
    _restore_core(core, mountain_state, bars, t2i)

    decision = core.on_bar(ctx)

    # persist state + surface cancels; keep transient _live for the caller's next set
    new_state = _extract_core(core, bars)
    new_state["last_bar_time"] = cur_time
    new_state["_live"] = mountain_state.get("_live")
    new_state["_cancel"] = list(getattr(decision, "cancel", []) or [])
    mountain_state.clear()
    mountain_state.update(new_state)

    if debug is not None and decision.cancel:
        debug["skip"] = f"cancel {len(decision.cancel)} pending (repeak/base_change/expiry)"

    if not decision.place:
        if debug is not None and not decision.cancel:
            debug["skip"] = debug.get("skip") or "no valid mountain"
        return None

    # ── build repo Signal from the placed LIMIT batch (BUY-only) ──
    entries = [EntryPoint(price=o.price, label=o.tag, lot=o.lot,
                          is_market=False, tp=o.tp, sl=o.sl) for o in decision.place]
    first = entries[0]
    entry, sl_price, tp_price = first.price, first.sl, first.tp
    risk_pip = abs(entry - sl_price) / PIP
    reward_pip = abs(tp_price - entry) / PIP
    rr = reward_pip / risk_pip if risk_pip > 0 else 0.0
    lot = round(sum(o.lot for o in decision.place), 2)
    r55 = _calc_r55(bars, len(bars) - 1, cfg["r55_bars"])
    a = core._armed or {}
    base_lo = a.get("base_lo", entry)
    height = a.get("height", 0.0)

    return Signal(
        pattern=PATTERN_NAME,
        direction="BUY",
        quality="✓",
        entry=entry,
        sl=sl_price,
        sl_name="SL_MTN_V3",
        tp_order=tp_price,
        tp_ref=tp_price,
        tp_name=f"TP {cfg['tp_pct_height']}%H",
        rr=rr,
        risk_pip=risk_pip,
        reward_pip=reward_pip,
        lot=lot,
        R55=r55,
        entries=entries,
        is_round2=False,
        father_pass="",
        vol_ratio=0.0,
        details={
            "order_type": "LIMIT",
            "pending_bars": cfg["pending_expiry_bars"],
            "base_lo": base_lo,
            "peak_hi": a.get("peak_hi", 0.0),
            "height": height,                       # pip (peak_hi - base_lo)
            "plan_id_core": a.get("plan_id"),
            # v3 has no trailing — default the removed keys so any lingering
            # is_mountain consumer doesn't KeyError until the trailing path is torn out
            "tp1": 0.0, "tp2_base": 0.0, "tech_point": base_lo,
            "swing_bar_nums": set(),
        },
    )
