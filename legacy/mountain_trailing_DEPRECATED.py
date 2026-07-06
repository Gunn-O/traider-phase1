"""
⛔ DEPRECATED — NOT WIRED. Kept for historical reference only.
   The old Mountain (v4.45/v67, 3-stage trailing SL: TP1→TP2→TP2+20%H) was
   replaced by Mountain v3 on the mountain-v3 swap. The live strategy is now
   strategies/mountain.py (v3 adapter) driving strategies/mountain_v3_core.py
   (source of truth: reference/mountain_v3_snapshot/). Mountain v3 has NO
   trailing — it closes at fixed %height SL/TP only. Do not import this module.

MOUNTAIN v4.45 / v67 — Mountain Round 1 (BUY only)

Port จาก XAUUSD_Backtest_v67.ipynb `_detect_mountain` (R1 path)
- Round 2 deprecated (state tracking ปิดใน signal_engine; config marked deprecated)
- ใช้ utils/swing_v414.scan_swings สำหรับ swing detection (เหมือน notebook)
- คืน utils.xauusd_signal.Signal เพื่อให้ pipeline G2/G3/G4 ใช้ได้ทันที

ความต่างจาก utils/xauusd_signal._detect_mountain (v4.20 เก่า):
  - Height threshold:  60% R55 (55% ถ้า adjacent base) — เก่า 50%
  - Peak selection:    max body_hi — เก่า max bar_nums (latest)
  - Buffer zone:       5% × height — เก่า 10%
  - SL formula:        entry − 60% × height — เก่า base_lo − 15%R55
  - TP base:           base_lo + height × {33%, 45%, 80%} — เก่า from entry
  - TP3:               base_lo + 80% × height — เก่า peak_hi (= 100%)
  - TP picker:         บังคับ TP3 — เก่า _pick_tp (R:R ≥ 1.0)
  - TP2 obstacle adj:  Wick / Body cluster + Swing Low — เก่าไม่มี
  - Spike check:       descent bars จาก > 50% line — เก่าไม่มี
  - Prev-bar zone:     L(prev_bar) < zone_lo → reject — เก่าไม่มี
"""
from __future__ import annotations
from typing import Optional, List, Tuple
import logging

from utils.xauusd_signal import OHLC, Signal
from utils.swing_v414 import scan_swings

logger = logging.getLogger(__name__)

PATTERN_NAME = "MOUNTAIN"

# ─── Constants (ตาม notebook v67) ────────────────────────────────
_TP3_REF_BUF = 0.10   # 10 pip
_TP3_ORD_BUF = 0.60   # 60 pip


# ════════════════════════════════════════════════════════════════
# Tuple helpers (match notebook layout: (bar_num, time, O, H, L, C))
# ════════════════════════════════════════════════════════════════

def _bars_to_tuples(bars: List[OHLC]) -> List[tuple]:
    out = []
    for i, b in enumerate(bars):
        bn = b.bar_num if b.bar_num else i + 1
        out.append((bn, b.time, b.open, b.high, b.low, b.close))
    return out


def _O(t): return t[2]
def _H(t): return t[3]
def _L(t): return t[4]
def _C(t): return t[5]


def _calc_lot(risk_pip: float, portfolio: float) -> float:
    if risk_pip <= 0:
        return 0.0
    return round((portfolio * 0.10) / risk_pip, 2)


# ════════════════════════════════════════════════════════════════
# v67 _detect_mountain (Round 1 only)
# ════════════════════════════════════════════════════════════════

def _detect_mountain_r1(
    window_t: List[tuple],
    all_t: List[tuple],
    R55: float,
    cur: tuple,
    used_swing_bars: Optional[set] = None,
    debug: Optional[dict] = None,
) -> Optional[Signal]:
    """
    ตรวจภูเขารอบ 1 → BUY (port v67 ตรง ๆ)

    debug: optional dict — เมื่อให้มา จะเขียน 'skip' = '<reason>' ทุก return None
           เพื่อให้ signal_engine surface reason ใน heartbeat (Tier 2).
    """
    def _skip(reason: str):
        if debug is not None:
            debug['skip'] = reason
        return None

    hs, ls = scan_swings(window_t, R55)
    if not hs or not ls:
        return _skip("ไม่เจอ swing high/low")

    # Base = LL ต่ำสุด (filter ตัวที่ใช้ entry แล้วถ้ามี)
    candidates = ls if not used_swing_bars else [
        s for s in ls
        if not any(bn in used_swing_bars for bn in s['bar_nums'])
    ]
    if not candidates:
        return _skip("base swings ใช้หมดแล้ว")
    base_sw = min(candidates, key=lambda s: s['body_lo'])

    # Peak = highest swing AFTER base — by body_hi (ไม่ใช่ bar_nums)
    peaks_after = [s for s in hs if s['bar_nums'][0] > base_sw['bar_nums'][-1]]
    if not peaks_after:
        return _skip("ไม่เจอ peak หลัง base")
    peak_sw = max(peaks_after, key=lambda s: s['body_hi'])

    base_lo = base_sw['body_lo']
    peak_hi = peak_sw['body_hi']
    height  = (peak_hi - base_lo) * 100  # pip

    # Adjacent base check — ถ้าฐานติดกับฐานเก่า ลด threshold เป็น 55%
    buf_check = min(height * 0.10, 100) / 100  # USD
    is_adjacent = False
    if used_swing_bars:
        prev_bases = [
            s for s in ls if any(bn in used_swing_bars for bn in s['bar_nums'])
        ]
        for pb in prev_bases:
            if abs(base_lo - pb['body_lo']) <= buf_check:
                is_adjacent = True
                break

    height_thresh = R55 * 0.55 if is_adjacent else R55 * 0.60
    if height < height_thresh:
        return _skip(f"height {height:.0f}p < {height_thresh:.0f}p (ภูเขาเล็ก)")

    # Entry zone: base_lo ± buffer (5% ของ height หรือ 100 pip)
    buf = min(height * 0.05, 100)
    zone_lo = base_lo - buf / 100
    zone_hi = base_lo + buf / 100

    # ขนาดภูเขา (X+Y) ≥ 10 bars
    X = peak_sw['bar_nums'][0] - base_sw['bar_nums'][-1]
    Y = cur[0] - peak_sw['bar_nums'][-1]
    if (X + Y) < 10:
        return _skip(f"ภูเขา {X+Y} bars < 10")

    # ห้ามมี Low ทะลุ thresh_10 ในช่วง 20-80% ของภูเขา
    thresh_10 = base_lo + (peak_hi - base_lo) * 0.20
    all_mid = [
        b for b in window_t
        if base_sw['bar_nums'][-1] < b[0] <= cur[0]
    ]
    total_bars = len(all_mid)
    if total_bars >= 3:
        lo20 = int(total_bars * 0.20)
        hi80 = int(total_bars * 0.80)
        for b in all_mid[lo20:hi80 + 1]:
            if _L(b) <= thresh_10:
                return _skip("Low ทะลุ thresh_10 ใน 20-80%")

    # ฐาน → entry ไม่เกิน 42 แท่ง
    bars_base_to_entry = cur[0] - base_sw['bar_nums'][-1]
    if bars_base_to_entry > 42:
        return _skip(f"base→entry {bars_base_to_entry} > 42 bars")

    # SH check — ถ้า > 25 แท่ง ต้องไม่มี SH หลัง peak มากกว่า 2 อัน
    if bars_base_to_entry > 25:
        peak_bar_last = peak_sw['bar_nums'][-1]
        sh_after_peak = [
            s for s in hs
            if peak_bar_last < s['bar_nums'][0] <= cur[0]
        ]
        if len(sh_after_peak) > 2:
            return _skip(f"SH หลัง peak {len(sh_after_peak)} > 2")

    # Spike check — descent bars: ห้ามมี O > 50%line และ L ≤ zone_hi
    H55_m = max(_H(b) for b in window_t)
    L55_m = min(_L(b) for b in window_t)
    line_50 = L55_m + (H55_m - L55_m) * 0.50
    peak_bar_last2 = peak_sw['bar_nums'][-1]
    descent_bars2 = [
        b for b in window_t if peak_bar_last2 < b[0] <= cur[0]
    ]
    for b in descent_bars2:
        if _O(b) > line_50 and _L(b) <= zone_hi:
            return _skip("spike ตอนลง (O>50% & L แตะ zone)")

    # Cur bar ต้องแตะ zone (low ≤ zone_hi และ high ≥ zone_lo)
    if not (_L(cur) <= zone_hi and _H(cur) >= zone_lo):
        return _skip(f"แท่งปัจจุบันยังไม่แตะ zone [{zone_lo:.2f}, {zone_hi:.2f}]")

    # Prev bar ห้าม break zone (ป้องกันราคาวิ่งผ่าน zone จากด้านบน)
    cur_idx = next(
        (i for i, b in enumerate(window_t) if b[0] == cur[0]), None
    )
    if cur_idx is not None and cur_idx > 0:
        prev_bar = window_t[cur_idx - 1]
        if _L(prev_bar) < zone_lo:
            return _skip("prev bar เจาะ zone จากบน")

    bars_since = cur[0] - peak_sw['bar_nums'][-1]
    entry = min(_H(cur), zone_hi)

    # ── TP from base_lo + height × percentage ─────────────
    dist     = peak_hi - base_lo
    tp1      = base_lo + dist * 0.33
    tp2_base = base_lo + dist * 0.45
    tp3r     = base_lo + dist * 0.80 - _TP3_REF_BUF
    tp3o     = base_lo + dist * 0.80 - _TP3_ORD_BUF

    # ── TP2 obstacle adjustment ──────────────────────────
    # 3 sources: Wick cluster, Body cluster, Swing Low above 40% height
    peak_bar_last = peak_sw['bar_nums'][-1]
    descent_bars = [
        b for b in window_t if peak_bar_last <= b[0] <= cur[0]
    ]

    obstacle_bottom: Optional[float] = None
    p4 = R55 * 0.04 / 100   # 4% R55 (USD)
    p5 = R55 * 0.05 / 100   # 5% R55 (USD)

    # 1. Wick Cluster: upper wick ≥ 3 bars > 5%R55, range tips ≤ 300 pip
    uw_bars = []
    for b in descent_bars:
        uw = (_H(b) - max(_O(b), _C(b))) * 100  # upper wick (pip)
        if uw > p5 * 100:
            uw_bars.append(_H(b))
    if len(uw_bars) >= 3:
        if (max(uw_bars) - min(uw_bars)) * 100 <= 300:
            obs = min(uw_bars) - p4
            if obs > tp1:
                obstacle_bottom = obs if obstacle_bottom is None else min(obstacle_bottom, obs)

    # 2. Body Cluster: ≥ 3 bars in any 10-bar window with overlapping body ranges
    for i in range(len(descent_bars)):
        group = descent_bars[i:i + 10]
        body_ranges = []
        for b in group:
            lo = min(_O(b), _C(b))
            hi = max(_O(b), _C(b))
            if (hi - lo) * 100 >= p5 * 100:
                body_ranges.append((lo, hi))
        if len(body_ranges) >= 3:
            overlap_lo = max(r[0] for r in body_ranges)
            overlap_hi = min(r[1] for r in body_ranges)
            if overlap_lo < overlap_hi:
                obs = overlap_lo - p4
                if obs > tp1:
                    obstacle_bottom = obs if obstacle_bottom is None else min(obstacle_bottom, obs)

    # 3. Swing Low above 40% height (after base, before cur)
    upper_thresh = base_lo + dist * 0.40
    _, ls_all = scan_swings(window_t, R55)
    for s in ls_all:
        if s['bar_nums'][0] <= base_sw['bar_nums'][-1]:
            continue
        if s['bar_nums'][-1] > cur[0]:
            continue
        if s['body_lo'] > upper_thresh:
            wick_lo = min(_L(b) for b in window_t if b[0] in s['bar_nums'])
            ref_price = min(s['body_lo'], wick_lo)
            obs = ref_price - p4
            if obs > tp1:
                obstacle_bottom = obs if obstacle_bottom is None else min(obstacle_bottom, obs)

    # ปรับ TP2: ถ้าเจอ obstacle อยู่ใต้ tp2_base → ใช้ obstacle, ถ้าอยู่เหนือ → ใช้ tp2_base
    has_obstacle = obstacle_bottom is not None and obstacle_bottom > tp1
    if has_obstacle:
        if tp2_base < obstacle_bottom:
            tp2     = tp2_base
            tp2_adj = None
        else:
            tp2_adj = obstacle_bottom
            tp2     = tp2_adj
    else:
        tp2_adj = None
        tp2     = tp2_base

    # ── SL = entry − 60% × height ────────────────────────
    _sl_dist = (peak_hi - base_lo) * 0.60
    sl       = entry - _sl_dist
    sl_name  = 'SL=60%H'
    risk_usd = _sl_dist  # USD
    if risk_usd <= 0:
        return None
    risk_pip = risk_usd * 100

    # ── TP forced TP3 (ไม่ใช้ _pick_tp) ──────────────────
    rr = abs(tp3r - entry) / risk_usd if risk_usd > 0 else 1.0
    tp_ref, tp_ord, tp_name = tp3r, tp3o, 'TP3'

    quality = '✓' if bars_since <= 40 else '⚠️ ช้า'

    return Signal(
        pattern    = PATTERN_NAME,
        direction  = 'BUY',
        quality    = quality,
        entry      = entry,
        sl         = sl,
        sl_name    = sl_name,
        tp_order   = tp_ord,
        tp_ref     = tp_ref,
        tp_name    = tp_name,
        rr         = rr,
        risk_pip   = risk_pip,
        reward_pip = abs(tp_ref - entry) * 100,
        R55        = R55,
        details    = {
            'base': base_sw, 'peak': peak_sw,
            'base_lo': base_lo, 'peak_hi': peak_hi,
            'height': height, 'buf': buf,
            'zone_lo': zone_lo, 'zone_hi': zone_hi,
            'bars_since_peak': bars_since,
            'tp1': tp1, 'tp2': tp2, 'tp3_ref': tp3r,
            'tp2_base': tp2_base, 'tp2_adj': tp2_adj,
            'is_adjacent': is_adjacent,
            'X': X, 'Y': Y,
            # Mountain is a zone-retest setup — broker must place a pending
            # LIMIT at entry (= min(H_cur, zone_hi)) and wait for price to
            # come back. main.py reads this; without it the default 'MARKET'
            # would fire the order at current price → wrong fill, wrong R:R.
            'order_type': 'LIMIT',
            # swing_bar_nums: tracked here (Signal class doesn't expose this field)
            'swing_bar_nums': set(base_sw['bar_nums']),
        },
    )


# ════════════════════════════════════════════════════════════════
# Public API — ตรงรูปแบบกับ xauusd_signal.find_signal
# ════════════════════════════════════════════════════════════════

def find_signal(
    bars: List[OHLC],
    portfolio: float = 1000.0,
    mountain_state: Optional[dict] = None,  # accepted for API compat; ignored (R2 deprecated)
    debug: Optional[dict] = None,
) -> Optional[Signal]:
    """
    หาสัญญาณ MOUNTAIN R1 จาก 55 แท่งล่าสุด

    mountain_state: รับเข้าเพื่อ backward-compat กับ xauusd_signal.find_signal
                    แต่ไม่ใช้ — Round 2 deprecated ใน v67
    debug:          optional dict — ถ้าให้มา จะเก็บ skip reason สำหรับ Tier 2

    Returns: Signal หรือ None
    """
    if len(bars) < 55:
        if debug is not None: debug['skip'] = f"bars {len(bars)} < 55"
        return None

    # assign bar_num ถ้ายังไม่มี
    for i, b in enumerate(bars):
        if b.bar_num == 0:
            b.bar_num = i + 1

    window = bars[-55:]
    window_t = _bars_to_tuples(window)
    all_t    = _bars_to_tuples(bars)
    cur_t    = window_t[-1]

    H55 = max(_H(b) for b in window_t)
    L55 = min(_L(b) for b in window_t)
    R55 = (H55 - L55) * 100

    if R55 == 0:
        if debug is not None: debug['skip'] = "R55=0 (flat market)"
        return None

    sig = _detect_mountain_r1(window_t, all_t, R55, cur_t, debug=debug)
    if sig is not None:
        sig.lot = _calc_lot(sig.risk_pip, portfolio)
    return sig
