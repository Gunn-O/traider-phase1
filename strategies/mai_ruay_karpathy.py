"""
MAI_RUAY (Karpathy / multi-TF) — Father/Mother v2.15M5_M1Karpathy

Port 1:1 ของ engine จาก notebook
`strategy/Mairuay_Basic_Father_V2.15M5_M1Karpathy.ipynb`.

Source of truth = engine code ใน cell 1 ของ notebook. Markdown header /
config cell ไม่ใช่ source of truth.

Pattern name: MAI_RUAY (multi-TF — M1/M5/M15/M30)
The M1-only V2.04 Bugfix1 variant lives in `strategies/mai_ruay.py`
under PATTERN_NAME = "MAI_RUAY_M1".

ความต่างหลักจาก V2.04 Bugfix1 (= MAI_RUAY_M1):
  - Father V1 style: 1-8 แท่ง, body รวม 60-100% R55, อนุญาตแทรก 1 ตัว
    body ≤ 5% R55, all-same length=5 ต้องมี trio open→close > 60% R55
  - ไม่มี Vol Ratio gate, ไม่มี per-bar body check
  - Mother: 4-30% ของ FATHER (notebook: "4-30% ของพ่อ") — NOT R55
  - ไม่มี R2 / Round 2 logic
  - Obstacle scanner (find_obstacle) active — 43-bar lookback
  - SL: obstacle ± 6%R55 OR tech ± 70%×f_body
  - TP: obstacle OR TP3 (75%×f_body) OR 45%×f_body special เมื่อ
    พ่อ>80%R55 + obs>60%พ่อ
  - TP30/SL45 special trigger เหมือนเดิม
  - Entries config: ENTRY_SMALL / ENTRY_MEDIUM lists (configurable)
    default = 2 entries per bucket (market + tech/mid)
  - ไม่มี pending queue 5 บาร์ — ถ้า LIMIT ไม่ fill บน child bar → discard
  - LIMIT gap-fill: ถ้า child.open ผ่าน limit price → fill ที่ child.open
  - ไม่มี TP per-entry RR>=1.0 adjustment
  - RR floor: ถ้า rr < 0.5 → ปรับ tp_sel ให้ rr = 0.5
  - ไม่มี lot adjustment (17-25%/2 หรือ >90%R55 ×2)
  - Obstacle→entry redirect: ถ้า obs_dist < TP1_dist → entry=tech_point
    และเหลือ 1 entry
"""
from __future__ import annotations
from typing import Optional, List, Tuple
import logging

from utils.xauusd_signal import OHLC, Signal, EntryPoint

logger = logging.getLogger(__name__)

PATTERN_NAME = "MAI_RUAY"

# ─── Constants (ตรงกับ notebook cell 1) ─────────────────────────────
PIP           = 0.01
RANGE_WINDOW  = 55
MAX_FATHER    = 8
RISK_PCT      = 0.10
PENDING_BARS  = 0   # Karpathy ไม่มี pending queue — child bar only

# ═══ Entry Configuration (ตรงกับ notebook constants) ══════════════
# เพิ่ม/ลบจุดเข้าได้โดยแก้ list ตรงนี้
# price: 'child_open' | 'mid_mother' | 'tech_point' | 'tech_far' | 'mother_close'
# is_market: True = fill ทันทีที่ open | False = LIMIT (ตรวจ fill บน child bar)
#
# tech_far = tech_point ∓ 10%×f_body (BUY: ลึกกว่า tech, SELL: สูงกว่า tech)
# ═══════════════════════════════════════════════════════════════════
ENTRY_SMALL: List[dict] = [  # แม่ 4-10% ของพ่อ
    {'name': 'market', 'price': 'child_open', 'is_market': True},
    {'name': 'tech',   'price': 'tech_point', 'is_market': False},
]
ENTRY_MEDIUM: List[dict] = [  # แม่ 10-30% ของพ่อ
    {'name': 'market',  'price': 'child_open', 'is_market': True},
    {'name': 'mid_mom', 'price': 'mid_mother', 'is_market': False},
]


# ════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════

def _calc_range55(bars: List[OHLC], end_idx: int) -> float:
    start = max(0, end_idx - RANGE_WINDOW + 1)
    window = bars[start:end_idx + 1]
    if not window:
        return 0.0
    hi = max(b.high for b in window)
    lo = min(b.low for b in window)
    return (hi - lo) / PIP


def _body_pips(b: OHLC) -> float:
    return abs(b.open - b.close) / PIP


def _is_bull(b: OHLC) -> bool: return b.close > b.open
def _is_bear(b: OHLC) -> bool: return b.close < b.open


# ════════════════════════════════════════════════════════════════
# Father — V1-style (1-8 bars, allow 1 opposite ≤5%R55, 60-100% R55)
# ════════════════════════════════════════════════════════════════

def _find_father(
    bars: List[OHLC], father_end: int, r55: float
) -> Optional[Tuple[int, int, str, float, str]]:
    """หาแท่งพ่อ 1-8 แท่ง ตาม notebook find_father V1 spec.

    เงื่อนไข:
      1. แท่งสุดท้าย (father_end) สีหลัก
      2. แท่งถัดไป (mother) ต้องสีสวนทาง
      3. ย้อนหลังไม่เกิน MAX_FATHER=8 แท่ง
      4. ภายใน run อนุญาตแท่งสีตรงข้ามได้ไม่เกิน 1 แท่ง body ≤ 5% R55
      5. body รวม (open แรก → close สุดท้าย) 60-100% R55
      6. เฉพาะพ่อ 5 แท่งสีเดียว: ต้องมี 3 แท่งติด open→close > 60% R55
    """
    if father_end < 0 or father_end >= len(bars):
        return None
    end_bar = bars[father_end]
    if   _is_bull(end_bar): run_dir = 'UP'
    elif _is_bear(end_bar): run_dir = 'DOWN'
    else: return None

    # แท่งถัดไป (แม่) ต้องสีสวนทาง
    if father_end + 1 < len(bars):
        nb = bars[father_end + 1]
        if (run_dir == 'UP'   and not _is_bear(nb)) or \
           (run_dir == 'DOWN' and not _is_bull(nb)):
            return None

    # ย้อนหลังหา run — อนุญาตแท่งสวน 1 ตัว body ≤ 5%R55
    opp_count  = 0
    opp_limit  = r55 * 0.05 * PIP  # 5% R55 (USD)
    run_start  = father_end
    for k in range(father_end - 1, max(-1, father_end - MAX_FATHER), -1):
        b = bars[k]
        same = (run_dir == 'UP' and _is_bull(b)) or (run_dir == 'DOWN' and _is_bear(b))
        if same:
            run_start = k
        else:
            b_body = _body_pips(b) * PIP
            if opp_count < 1 and b_body <= opp_limit:
                opp_count += 1
                run_start = k
            else:
                break

    length = father_end - run_start + 1
    if length > MAX_FATHER:
        return None
    # พ่อ 1-5 แท่ง ห้ามมีแท่งสวนทิศเลย
    if length <= 5 and opp_count > 0:
        return None

    f_start    = run_start
    total_body = abs(bars[f_start].open - bars[father_end].close) / PIP
    pct        = total_body / r55 * 100 if r55 > 0 else 0
    if not (60 <= pct <= 100):
        return None

    # all-same length=5 → ต้องมี 3 แท่งติด open→close > 60% R55
    all_same = all(
        (run_dir == 'UP' and _is_bull(bars[j])) or
        (run_dir == 'DOWN' and _is_bear(bars[j]))
        for j in range(f_start, father_end + 1)
    )
    if all_same and length == 5:
        has_trio = any(
            abs(bars[j].open - bars[j+2].close) / PIP > r55 * 0.60
            for j in range(f_start, father_end - 1)
        )
        if not has_trio:
            return None

    return (f_start, father_end, run_dir, total_body, 'Pass1 V1.5 1-8แท่ง 60-100%R55')


# ════════════════════════════════════════════════════════════════
# Mother — V1-style (4-30% ของพ่อ — NOT R55)
# ════════════════════════════════════════════════════════════════

def _validate_mother(
    bars: List[OHLC], mother_idx: int, father_dir: str, father_body: float
) -> Optional[Tuple[float, float, str]]:
    """แท่งแม่: สวนทิศพ่อ, body 4-30% ของ FATHER (notebook V1 reference).

    Returns: (mother_body_pips, mother_pct_father, quality_label) หรือ None
    """
    if mother_idx < 0 or mother_idx >= len(bars):
        return None
    m = bars[mother_idx]
    m_body = _body_pips(m)
    if father_dir == 'UP'   and not _is_bear(m): return None
    if father_dir == 'DOWN' and not _is_bull(m): return None
    if father_body <= 0:
        return None
    pct = m_body / father_body * 100
    if pct < 4 or pct > 30:
        return None
    quality = (
        f"สวยที่สุด ({pct:.1f}%) ✅✅" if pct <= 20 else
        f"ใช้ได้     ({pct:.1f}%) ✅"
    )
    return (m_body, pct, quality)


# ════════════════════════════════════════════════════════════════
# Obstacle scanner (find_obstacle)
# ════════════════════════════════════════════════════════════════

def _swing_bsize(o, c): return abs(o - c) / PIP
def _swing_bhi(o, c):   return max(o, c)
def _swing_blo(o, c):   return min(o, c)


def _swing_check_high(bars_arr, li, rj, mid, thick_exc=False):
    left_range  = [li-1] if thick_exc else [li-3, li-2, li-1]
    right_range = [rj+1] if thick_exc else [rj+1, rj+2]
    for k in left_range:
        if k < 0: continue
        if bars_arr[k][0] >= mid or bars_arr[k][1] >= mid: return False
    for k in right_range:
        if k >= len(bars_arr): return True
        if bars_arr[k][0] >= mid or bars_arr[k][1] >= mid: return False
    return True


def _swing_check_low(bars_arr, li, rj, mid, thick_exc=False):
    left_range  = [li-1] if thick_exc else [li-3, li-2, li-1]
    right_range = [rj+1] if thick_exc else [rj+1, rj+2]
    for k in left_range:
        if k < 0: continue
        if bars_arr[k][0] <= mid or bars_arr[k][1] <= mid: return False
    for k in right_range:
        if k >= len(bars_arr): return True
        if bars_arr[k][0] <= mid or bars_arr[k][1] <= mid: return False
    return True


def _find_obstacle(
    bars: List[OHLC],
    father_start: int,
    r55_start: int,
    entry: float,
    tp3: float,
    direction: str,
    father_body_pips: float,
    tech_point: float,
    r55: float,
) -> Tuple[Optional[float], str]:
    """หาอุปสรรค swing high/low ระหว่าง r55_start..father_start."""
    scan = bars[r55_start:father_start]
    n = len(scan)
    if n < 4:
        return None, 'แท่งไม่พอ'

    buf         = r55 * 0.06 * PIP
    min_dist    = r55 * 0.20 * PIP
    thresh1     = r55 * 0.01
    thresh10    = r55 * 0.10
    pair_thresh = max(r55 * 0.01, 100) / PIP

    bars_arr = [(b.open, b.close) for b in scan]
    seen = set()
    candidates: List[Tuple[int, float, str]] = []

    def try_pair(li, rj, c1o, c1c, c3o, c3c, t_rj):
        key = (li, rj)
        if key in seen: return
        if abs(c1c - c3o) > pair_thresh: return
        b1 = _swing_bsize(c1o, c1c)
        b3 = _swing_bsize(c3o, c3c)
        if b1 < thresh1 or b3 < thresh1: return
        mid   = (c1c + c3o) / 2
        thick = b1 > thresh10 or b3 > thresh10
        seen.add(key)

        if direction == 'SELL':
            h1 = scan[li].high if li < len(scan) else _swing_bhi(c1o, c1c)
            h3 = scan[rj].high if rj < len(scan) else _swing_bhi(c3o, c3c)
            obs_p = max(h1, h3)
            if not (tp3 < obs_p < entry): return
            if abs(tech_point - obs_p) < min_dist: return
            if _swing_check_high(bars_arr, li, rj, mid, thick_exc=thick):
                candidates.append((rj, obs_p, t_rj))
        else:
            l1 = scan[li].low if li < len(scan) else _swing_blo(c1o, c1c)
            l3 = scan[rj].low if rj < len(scan) else _swing_blo(c3o, c3c)
            obs_p = min(l1, l3)
            if not (entry < obs_p < tp3): return
            if abs(obs_p - tech_point) < min_dist: return
            if _swing_check_low(bars_arr, li, rj, mid, thick_exc=thick):
                candidates.append((rj, obs_p, t_rj))

    for i in range(n - 1):
        j = i + 1
        ri, rj = scan[i], scan[j]
        bi_sz = _swing_bsize(ri.open, ri.close)
        bj_sz = _swing_bsize(rj.open, rj.close)
        t_j   = str(rj.time)[:16]
        doji_i = bi_sz < thresh1
        doji_j = bj_sz < thresh1

        if not doji_i and not doji_j:
            try_pair(i, j, ri.open, ri.close, rj.open, rj.close, t_j)
        elif not doji_i and doji_j and j + 1 < n:
            rk = scan[j + 1]
            try_pair(i, j + 1, ri.open, ri.close, rk.open, rk.close, str(rk.time)[:16])
        elif doji_i and not doji_j and i - 1 >= 0:
            rh = scan[i - 1]
            try_pair(i - 1, j, rh.open, rh.close, rj.open, rj.close, t_j)

    if not candidates:
        return None, 'ไม่มี Swing ในเส้นทาง TP'

    if direction == 'SELL':
        best = max(candidates, key=lambda x: x[1])
    else:
        best = min(candidates, key=lambda x: x[1])
    _, obs_price, t_obs = best
    if direction == 'SELL':
        return obs_price + buf, f"Swing High={obs_price:.3f} @ {t_obs}"
    return obs_price - buf, f"Swing Low={obs_price:.3f} @ {t_obs}"


# ════════════════════════════════════════════════════════════════
# SL / TP helpers (V1-style)
# ════════════════════════════════════════════════════════════════

def _calc_sl_70(tech: float, direction: str, father_body_pips: float) -> Tuple[float, str]:
    """SL fallback = 70% ของพ่อ from tech_point (no obstacle case)."""
    offset = father_body_pips * 0.70 * PIP
    if direction == 'BUY':
        sl = tech - offset
        return sl, f"tech−70%พ่อ({father_body_pips*0.70:.0f}pip)"
    sl = tech + offset
    return sl, f"tech+70%พ่อ({father_body_pips*0.70:.0f}pip)"


def _calc_tp_candidates(tech: float, father_body_pips: float, direction: str) -> Tuple[float, float, float]:
    """TP1=33%, TP2=50%, TP3=75% ของพ่อ (จาก tech_point)."""
    sign = 1 if direction == 'BUY' else -1
    f    = father_body_pips * PIP
    return (tech + sign * (f * 0.33),
            tech + sign * (f * 0.50),
            tech + sign * (f * 0.75))


def _calc_lot(portfolio: float, sl_pips: float) -> float:
    if sl_pips <= 0:
        return 0.0
    return round((portfolio * RISK_PCT) / sl_pips, 2)


# ════════════════════════════════════════════════════════════════
# Core analyzer (1 bar)
# ════════════════════════════════════════════════════════════════

def _analyze_bar(
    bars: List[OHLC],
    bar_idx: int,
    portfolio: float,
    debug: Optional[dict] = None,
) -> Optional[Signal]:
    """Port ของ notebook analyze_bar (Karpathy)."""
    def _skip(reason: str):
        if debug is not None:
            debug['skip'] = reason
        return None

    if bar_idx < RANGE_WINDOW - 1:
        return _skip(f"bar_idx {bar_idx} < {RANGE_WINDOW-1}")
    mother_idx = bar_idx - 1
    father_end = bar_idx - 2
    if father_end < 0:
        return _skip("father_end < 0")

    # 1. R55 (ณ จบแท่งแม่)
    r55 = _calc_range55(bars, bar_idx - 1)
    if r55 <= 0:
        return _skip("R55 <= 0")

    # 2. แท่งพ่อ
    fr = _find_father(bars, father_end, r55)
    if fr is None:
        return _skip("ไม่เจอ father (1-8 bars, 60-100%R55, opp ≤5%R55)")
    f_start, f_end, f_dir, f_body, f_pass = fr

    # Vol Ratio (recorded for details, not gated)
    _f_bar_count = f_end - f_start + 1
    _f_avg_body  = f_body / _f_bar_count if _f_bar_count > 0 else 0
    _pre20_start = max(0, f_start - 20)
    _pre20 = bars[_pre20_start:f_start]
    if len(_pre20) > 0:
        _pre20_avg = sum(_body_pips(b) for b in _pre20) / len(_pre20)
        _vol_ratio = round(_f_avg_body / _pre20_avg, 2) if _pre20_avg > 0 else 0.0
    else:
        _vol_ratio = 0.0

    _f_first_body = abs(bars[f_start].open - bars[f_start].close) / PIP
    _f_first_pct  = _f_first_body / r55 * 100 if r55 > 0 else 0

    # 3. แท่งแม่ (4-30% ของพ่อ — NOT R55)
    mr = _validate_mother(bars, mother_idx, f_dir, f_body)
    if mr is None:
        return _skip("mother ไม่ผ่าน (สวนทิศ + body 4-30% ของพ่อ)")
    m_body, m_pct, m_quality = mr

    # 4. ทิศทาง (ไม่มี anti-trend)
    direction = 'BUY' if f_dir == 'DOWN' else 'SELL'

    # 5. Entry seed
    m_row        = bars[mother_idx]
    father_close = bars[f_end].close
    mother_open  = m_row.open
    mother_close = m_row.close
    tech_point   = (father_close + mother_open) / 2
    buffer_pips  = min(100.0, f_body * 0.05)
    mid_mother   = (mother_open + mother_close) / 2
    child        = bars[bar_idx]

    # 6. Build entries from config
    _price_map = {
        'child_open':   child.open,
        'mother_close': mother_close,
        'mid_mother':   mid_mother,
        'tech_point':   tech_point,
        'tech_far':     (tech_point - f_body * 0.10 * PIP) if direction == 'BUY'
                        else (tech_point + f_body * 0.10 * PIP),
    }
    if 4 <= m_pct < 10:
        _cfg = ENTRY_SMALL
    elif 10 <= m_pct <= 30:
        _cfg = ENTRY_MEDIUM
    else:
        return _skip(f"m_pct {m_pct:.1f}% out of [4, 30]")

    _entries: List[Tuple[float, str, bool]] = []
    for _ec in _cfg:
        _ep = _price_map[_ec['price']]
        _er = f"{_ec['name']}({_ep:.3f})"
        _mkt = bool(_ec['is_market'])
        _entries.append((_ep, _er, _mkt))

    if not _entries:
        return _skip("entries config empty")

    # 6b. Fill check on child bar — limit entries discarded if not touched.
    # Gap-fill: ถ้า child.open ผ่าน limit price ทันที → fill ที่ child.open
    # (= ราคาเปิด)
    _filled_entries: List[Tuple[float, str, bool]] = []
    _any_fill = False
    for _ep, _er, _mkt in _entries:
        if _mkt:
            _filled_entries.append((_ep, _er, _mkt))
            _any_fill = True
        else:
            _limit = _ep
            if direction == 'BUY' and child.low <= _limit:
                if child.open <= _limit:
                    _ep_fill = child.open
                    _er_fill = _er + f' [fill@open {child.open:.3f}]'
                else:
                    _ep_fill = _limit
                    _er_fill = _er
                _filled_entries.append((_ep_fill, _er_fill, _mkt))
                _any_fill = True
            elif direction == 'SELL' and child.high >= _limit:
                if child.open >= _limit:
                    _ep_fill = child.open
                    _er_fill = _er + f' [fill@open {child.open:.3f}]'
                else:
                    _ep_fill = _limit
                    _er_fill = _er
                _filled_entries.append((_ep_fill, _er_fill, _mkt))
                _any_fill = True
    if not _any_fill:
        return _skip("ไม่มี entry ใดที่ fill บน child bar")
    _entries = _filled_entries
    entry      = _entries[0][0]
    entry_rule = _entries[0][1]

    # 7. TP candidates + obstacle scan
    tp1, tp2, tp3 = _calc_tp_candidates(tech_point, f_body, direction)
    r55_start = max(0, bar_idx - RANGE_WINDOW + 1)
    obs_limit = bar_idx - 43
    obs_start = max(r55_start, obs_limit)
    if f_start <= obs_start:
        obs, obs_label = None, 'พ่ออยู่นอกขอบ 43 แท่ง'
    else:
        obs, obs_label = _find_obstacle(
            bars, f_start, obs_start, entry, tp3, direction, f_body,
            tech_point=tech_point, r55=r55,
        )

    # 7b. obs < TP1 → entry redirect to tech_point (single entry)
    if obs is not None:
        tp1_dist = abs(tp1 - tech_point)
        obs_dist_check = abs(obs - tech_point)
        if obs_dist_check < tp1_dist:
            entry      = tech_point
            entry_rule = f'obs < TP1 → entry = tech_point ({tech_point:.3f})'
            _entries   = [(tech_point, entry_rule, False)]

    # 8. SL
    if obs is not None:
        _sl_buf   = r55 * 0.06 * PIP
        _sl_swing = (obs - _sl_buf) if direction == 'SELL' else (obs + _sl_buf)
        _obs_dist = abs(_sl_swing - tech_point) / PIP
        offset    = _obs_dist * PIP
        if direction == 'BUY':
            sl = tech_point - offset
            sl_label = f'tech−swing_dist({_obs_dist:.0f}pip)'
        else:
            sl = tech_point + offset
            sl_label = f'tech+swing_dist({_obs_dist:.0f}pip)'
    else:
        sl, sl_label = _calc_sl_70(tech_point, direction, f_body)

    sl_pips = abs(entry - sl) / PIP
    if sl_pips < 1:
        return _skip(f"sl_pips {sl_pips:.1f} < 1")

    # 9. TP selection
    if obs is not None:
        _obs_buf      = r55 * 0.06 * PIP
        _swing_price  = (obs - _obs_buf) if direction == 'SELL' else (obs + _obs_buf)
        _obs_dist_pip = abs(_swing_price - tech_point) / PIP
        _f_pct2       = f_body / r55 * 100
        if _f_pct2 > 80 and _obs_dist_pip > f_body * 0.60:
            tp_sel = (tech_point + f_body * 0.45 * PIP) if direction == 'BUY' \
                     else (tech_point - f_body * 0.45 * PIP)
            tp_lbl = 'TP 45% (พ่อ>80%R55 + obs>60%พ่อ)'
        else:
            tp_sel = obs
            tp_lbl = 'TP_adj (ก่อนอุปสรรค)'
    else:
        tp_sel = tp3
        tp_lbl = 'TP3 (75% พ่อ)'

    # 10. TP30/SL45 special — เปิดเสมอ (notebook: if True)
    _pre50_start = max(0, f_start - 50)
    _pre50       = bars[_pre50_start:f_start]
    _r55_start_w = max(0, bar_idx - RANGE_WINDOW)
    _r55_window  = bars[_r55_start_w:bar_idx]
    if _r55_window and _pre50:
        _low55  = min(b.low for b in _r55_window)
        _high55 = max(b.high for b in _r55_window)
        _level60 = _low55 + r55 * 0.60 * PIP
        _level40 = _low55 + r55 * 0.40 * PIP
        _tp30_trigger = False
        if direction == 'BUY':
            if min(b.low for b in _pre50) >= _level60:
                _tp30_trigger = True
        else:
            if max(b.high for b in _pre50) <= _level40:
                _tp30_trigger = True
        if _tp30_trigger:
            if direction == 'BUY':
                tp_sel = tech_point + f_body * 0.30 * PIP
                sl     = tech_point - f_body * 0.45 * PIP
            else:
                tp_sel = tech_point - f_body * 0.30 * PIP
                sl     = tech_point + f_body * 0.45 * PIP
            tp_lbl   = 'TP 30% (50แท่งก่อนพ่อ)'
            sl_label = f'SL 45%พ่อ tp30_trigger ({f_body*0.45:.0f}pip)'
            sl_pips  = abs(entry - sl) / PIP

    # 11. TP minimum filter
    tp_pips = abs(tp_sel - entry) / PIP
    if tp_pips < 200:
        return _skip(f"TP {tp_pips:.0f} pip < 200")

    rr = tp_pips / sl_pips if sl_pips > 0 else 0.0
    # 11b. RR floor 0.5
    if rr < 0.5 and sl_pips > 0:
        tp_pips = sl_pips * 0.5
        if direction == 'BUY':
            tp_sel = entry + tp_pips * PIP
        else:
            tp_sel = entry - tp_pips * PIP
        tp_lbl += ' → ปรับ R:R=0.5'
        rr = 0.5

    lot = _calc_lot(portfolio, sl_pips)
    # NOTE: Karpathy ไม่มี lot adjustment (17-25%/2, >90%R55 ×2) — ปล่อย raw

    # 12. Auto-split lot across entries (per notebook: round(lot/len, 2))
    _n = len(_entries)
    _lot_each = round(lot / _n, 2) if (_n > 0 and lot > 0) else 0.0

    entries_full = []
    for _ep, _er, _mkt in _entries:
        # Karpathy ไม่ทำ TP per-entry adjustment — ใช้ tp_sel เดียวกัน
        entries_full.append(EntryPoint(
            price     = _ep,
            label     = _er,
            lot       = _lot_each,
            is_market = _mkt,
            tp        = tp_sel,
            sl        = sl,
        ))

    bar_num = lambda i: bars[i].bar_num if bars[i].bar_num else i + 1

    return Signal(
        pattern    = PATTERN_NAME,
        direction  = direction,
        # quality: ใช้ symbol แบบเดียวกับ engines อื่น เพื่อให้ G2 _parse_quality ใช้ได้
        quality    = "✓" if m_pct <= 20 else "~60%⚠️",
        entry      = entry,
        sl         = sl,
        sl_name    = 'SL_KARP',
        # ไม่มี spread buffer ใน Karpathy notebook — tp_order = tp_ref = tp_sel
        tp_order   = tp_sel,
        tp_ref     = tp_sel,
        tp_name    = tp_lbl,
        rr         = rr,
        risk_pip   = sl_pips,
        reward_pip = tp_pips,
        lot        = lot,
        R55        = r55,
        entries     = entries_full,
        is_round2   = False,  # Karpathy ไม่มี R2
        father_pass = f_pass,
        vol_ratio   = _vol_ratio,
        details    = {
            'father_start': f_start, 'father_end': f_end,
            'father_bars': f_end - f_start + 1,
            'father_body_pips': f_body, 'father_pct_r55': f_body / r55 * 100,
            'father_first_pct': round(_f_first_pct, 1),
            'mother_idx': mother_idx, 'mother_body_pips': m_body,
            'mother_pct_father': m_pct,         # Karpathy field name
            'mother_pct_r55': m_pct,            # alias for downstream tools that read R55 name
            'mother_quality': m_quality,
            'tech_point': tech_point, 'buffer_pips': buffer_pips,
            'entry_rule': entry_rule, 'sl_label': sl_label,
            'tp1': tp1, 'tp2': tp2, 'tp3': tp3,
            'obstacle': obs, 'obstacle_label': obs_label,
            # main.py reads order_type for the 1st entry MARKET vs LIMIT routing.
            'order_type': 'MARKET' if entries_full[0].is_market else 'LIMIT',
            # Karpathy = no pending wait (child bar only). main.py:add_orders
            # checks order['pending_bars']; setting 0 means "expire immediately
            # next bar" — but since Karpathy LIMITs that didn't fill on child
            # bar are already discarded by analyze_bar above, this only matters
            # for backtest simulation where the order would otherwise sit.
            'pending_bars': 0,
            'tp_cancel_buffer_pips': 0.0,
            'swing_bar_nums': {bar_num(f_start), bar_num(f_end), bar_num(mother_idx)},
        },
    )


# ════════════════════════════════════════════════════════════════
# Public API — ตรงรูปแบบกับ strategies.mai_ruay.find_signal
# ════════════════════════════════════════════════════════════════

def find_signal(
    bars: List[OHLC],
    portfolio: float = 1000.0,
    debug: Optional[dict] = None,
    # Karpathy ไม่มี R2 — accept round2_info param ไว้เผื่อ signal_engine
    # ส่งมา (จะ ignore)
    round2_info: Optional[dict] = None,
) -> Optional[Signal]:
    """หาสัญญาณ MAI_RUAY (Karpathy) ที่แท่งสุดท้าย bars[-1]."""
    if round2_info is not None:
        # Karpathy ไม่มี R2 — ส่ง round2_info มาก็ skip ออกเลย
        if debug is not None:
            debug['skip'] = 'Karpathy: no R2 logic'
        return None
    if len(bars) < RANGE_WINDOW:
        if debug is not None:
            debug['skip'] = f"bars {len(bars)} < {RANGE_WINDOW}"
        return None

    for i, b in enumerate(bars):
        if b.bar_num == 0:
            b.bar_num = i + 1

    return _analyze_bar(bars, len(bars) - 1, portfolio, debug=debug)
