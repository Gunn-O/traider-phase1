"""
MAI_RUAY (ไม้รวย) — Father/Mother candle pattern (Branch F)

Port ของ engine จาก XAUUSD_Backtest_MaiRuay notebook โดยปรับ input/output ให้
เข้ากับ pipeline หลัก (รับ list[OHLC], คืน Signal ของ xauusd_signal)

Logic หลัก (ตาม notebook):
  - ไม้พ่อ: 1-5 แท่ง สีเดียวกัน body 50-100% R55
  - ไม้แม่: สวนทิศพ่อ body 4-30% ของพ่อ
  - SL = tech_point ± 70% ของ body พ่อ
  - TP1=33%, TP2=50%, TP3=75% ของ body พ่อ — ค่า default ใช้ TP3
    ถ้ามีอุปสรรค (Swing Low/High) → TP_adj = อุปสรรค ± buffer 6%R55
  - Lot = portfolio × 10% / SL_pip
"""
from __future__ import annotations
from typing import Optional, List, Tuple
import logging

from utils.xauusd_signal import OHLC, Signal

logger = logging.getLogger(__name__)

PATTERN_NAME = "MAI_RUAY"

# ─── Constants (ตรงกับ notebook) ─────────────────────────────────
PIP           = 0.01
RANGE_WINDOW  = 55
MAX_FATHER    = 8
RISK_PCT      = 0.10

# Spread buffer (mirror Mountain v67) — direction-aware ใน _analyze_bar
# tp_ref:   ใช้คำนวณ R:R (ใกล้กับเป้าจริง 10 pip)
# tp_order: ราคาที่ส่งให้ broker (ห่างกว่า 60 pip เพื่อ ensure fill ใน Cent spread)
_TP_REF_BUF = 0.10  # USD = 10 pip
_TP_ORD_BUF = 0.60  # USD = 60 pip (ครอบคลุม Cent spread ปกติ ~28 pip + buffer 32)


# ════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════

def _calc_range55(bars: List[OHLC], end_idx: int) -> float:
    """Range55 = (max High − min Low) / pip ในหน้าต่าง 55 แท่ง สิ้นสุดที่ end_idx"""
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


def _detect_trend(bars: List[OHLC], end_idx: int) -> str:
    """Slope ง่ายๆ จาก 20 แท่งล่าสุด — UP/DOWN/NONE"""
    lookback = min(20, end_idx)
    if lookback < 5:
        return 'NONE'
    w = bars[end_idx - lookback:end_idx + 1]
    highs = [b.high for b in w]
    lows  = [b.low  for b in w]
    n = len(highs) - 1
    if n <= 0:
        return 'NONE'
    hh = sum(1 for i in range(1, len(highs)) if highs[i] > highs[i-1])
    hl = sum(1 for i in range(1, len(lows))  if lows[i]  > lows[i-1])
    lh = sum(1 for i in range(1, len(highs)) if highs[i] < highs[i-1])
    ll = sum(1 for i in range(1, len(lows))  if lows[i]  < lows[i-1])
    if hh / n > 0.55 and hl / n > 0.45: return 'UP'
    if ll / n > 0.55 and lh / n > 0.45: return 'DOWN'
    return 'NONE'


# ════════════════════════════════════════════════════════════════
# Pattern detection
# ════════════════════════════════════════════════════════════════

def _find_father(
    bars: List[OHLC], father_end: int, r55: float
) -> Optional[Tuple[int, int, str, float]]:
    """
    หาไม้พ่อ (run 1-8 แท่ง สีเดียวกัน body 60-100% R55)
    คืน (start_idx, end_idx, direction, total_body_pips) หรือ None
    """
    end_bar = bars[father_end]
    if   _is_bull(end_bar): run_dir = 'UP'
    elif _is_bear(end_bar): run_dir = 'DOWN'
    else: return None

    # แท่งถัดจากพ่อ ต้องสีสวนทาง
    if father_end + 1 < len(bars):
        nxt = bars[father_end + 1]
        if (run_dir == 'UP'   and not _is_bear(nxt)) or \
           (run_dir == 'DOWN' and not _is_bull(nxt)):
            return None

    # ย้อนหลัง run
    opp_count = 0
    opp_limit = r55 * 0.05 * PIP  # 5% R55
    run_start = father_end
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

    if length <= 5 and opp_count > 0:
        return None

    f_start    = run_start
    span_open  = bars[f_start].open
    span_close = bars[father_end].close
    total_body = abs(span_open - span_close) / PIP
    pct        = total_body / r55 * 100 if r55 > 0 else 0
    if not (60 <= pct <= 100):
        return None

    # ถ้า all-same length=5: ต้องมี 3 แท่งติดกัน open→close > 50% R55
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

    return (f_start, father_end, run_dir, total_body)


def _validate_mother(
    bars: List[OHLC], mother_idx: int, father_dir: str, father_body: float
) -> Optional[Tuple[float, float, str]]:
    """
    ไม้แม่: สวนทิศพ่อ body 4-30% ของพ่อ
    คืน (mother_body_pips, mother_pct_father, quality_label) หรือ None
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
    quality = "สวยดี" if pct <= 20 else "ใหญ่ไป"
    return (m_body, pct, quality)


# ════════════════════════════════════════════════════════════════
# SL / TP / Obstacle
# ════════════════════════════════════════════════════════════════

def _calc_sl(tech: float, direction: str, father_body_pips: float) -> Tuple[float, str]:
    offset = father_body_pips * 0.70 * PIP
    if direction == 'BUY':
        sl = tech - offset
        return sl, f"tech−ก่อ×70% = {sl:.3f}"
    sl = tech + offset
    return sl, f"tech+ก่อ×70% = {sl:.3f}"


def _calc_tp(tech: float, father_body_pips: float, direction: str) -> Tuple[float, float, float]:
    sign = 1 if direction == 'BUY' else -1
    f = father_body_pips * PIP
    return (tech + sign * (f * 0.33),
            tech + sign * (f * 0.50),
            tech + sign * (f * 0.75))


def _calc_lot(portfolio: float, sl_pips: float) -> float:
    if sl_pips <= 0:
        return 0.0
    return round((portfolio * RISK_PCT) / sl_pips, 2)


# ─── Mini swing detector for obstacles (port จาก notebook) ────
def _swing_bsize(o, c): return abs(o - c) / PIP
def _swing_bhi(o, c):   return max(o, c)
def _swing_blo(o, c):   return min(o, c)


def _swing_check_high(bars_arr, li, rj, mid, thick_exc=False):
    left  = [li-1] if thick_exc else [li-3, li-2, li-1]
    right = [rj+1] if thick_exc else [rj+1, rj+2]
    for k in left:
        if k < 0: continue
        if bars_arr[k][0] >= mid or bars_arr[k][1] >= mid: return False
    for k in right:
        if k >= len(bars_arr): return True
        if bars_arr[k][0] >= mid or bars_arr[k][1] >= mid: return False
    return True


def _swing_check_low(bars_arr, li, rj, mid, thick_exc=False):
    left  = [li-1] if thick_exc else [li-3, li-2, li-1]
    right = [rj+1] if thick_exc else [rj+1, rj+2]
    for k in left:
        if k < 0: continue
        if bars_arr[k][0] <= mid or bars_arr[k][1] <= mid: return False
    for k in right:
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
    """
    หา Swing High/Low ระหว่าง r55_start..father_start ที่อยู่ระหว่าง entry กับ tp3
    ถ้าเจอ → คืน price + buffer 6%R55 เป็น TP_adj
    """
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
    candidates = []

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
        return None, 'ไม่มี Swing ขวางทาง TP'

    if direction == 'SELL':
        best = max(candidates, key=lambda x: x[1])
    else:
        best = min(candidates, key=lambda x: x[1])
    _, obs_price, t_obs = best
    if direction == 'SELL':
        return obs_price + buf, f"Swing High={obs_price:.3f} @ {t_obs}"
    return obs_price - buf, f"Swing Low={obs_price:.3f} @ {t_obs}"


# ════════════════════════════════════════════════════════════════
# Core analyzer (1 bar)
# ════════════════════════════════════════════════════════════════

def _analyze_bar(bars: List[OHLC], bar_idx: int, portfolio: float) -> Optional[Signal]:
    """Wrapper analyze_bar จาก notebook → Signal"""
    if bar_idx < RANGE_WINDOW - 1:
        return None
    mother_idx = bar_idx - 1
    father_end = bar_idx - 2
    if father_end < 0:
        return None

    r55 = _calc_range55(bars, bar_idx)
    if r55 <= 0:
        return None

    fr = _find_father(bars, father_end, r55)
    if fr is None: return None
    f_start, f_end, f_dir, f_body = fr

    mr = _validate_mother(bars, mother_idx, f_dir, f_body)
    if mr is None: return None
    m_body, m_pct, m_quality = mr

    trend = _detect_trend(bars, bar_idx)
    direction = 'BUY' if f_dir == 'DOWN' else 'SELL'
    if trend == 'UP'   and direction == 'SELL': return None
    if trend == 'DOWN' and direction == 'BUY':  return None

    m_row        = bars[mother_idx]
    father_close = bars[f_end].close
    mother_open  = m_row.open
    mother_close = m_row.close
    tech_point   = (father_close + mother_open) / 2
    buffer_pips  = min(100.0, f_body * 0.05)

    mid_mother = (mother_open + mother_close) / 2
    if   4 <= m_pct < 10:
        entry_price = mother_close
        entry_rule  = f"แม่ {m_pct:.1f}% → close แม่"
    elif 10 <= m_pct < 30:
        entry_price = mid_mother
        entry_rule  = f"แม่ {m_pct:.1f}% → midpoint"
    else:
        entry_price = tech_point
        entry_rule  = f"แม่ {m_pct:.1f}% → tech_point"

    child = bars[bar_idx]
    buf_price = buffer_pips * PIP

    if direction == 'BUY':
        entry = entry_price + buf_price
        if child.low > entry:
            return None
    else:
        entry = entry_price - buf_price
        if child.high < entry:
            return None

    tp1, tp2, tp3 = _calc_tp(tech_point, f_body, direction)

    r55_start = max(0, bar_idx - RANGE_WINDOW + 1)
    obs_limit = bar_idx - 43
    obs_start = max(r55_start, obs_limit)

    if f_start <= obs_start:
        obs, obs_label = None, 'ก่อข้างหน้าเกิน 43 แท่ง'
    else:
        obs, obs_label = _find_obstacle(
            bars, f_start, obs_start, entry, tp3, direction, f_body,
            tech_point=tech_point, r55=r55,
        )

    # ปรับ entry ถ้าอุปสรรคใกล้กว่า TP1
    if obs is not None:
        tp1_dist = abs(tp1 - tech_point)
        obs_dist = abs(obs - tech_point)
        if obs_dist < tp1_dist:
            entry      = tech_point
            entry_rule = f'obs < TP1 → entry = tech_point'

    # SL
    if obs is not None:
        obs_dist = abs(obs - tech_point) / PIP
        offset   = obs_dist * PIP
        if direction == 'BUY':
            sl = tech_point - offset
            sl_label = f'tech−obs_dist({obs_dist:.0f}pip)'
        else:
            sl = tech_point + offset
            sl_label = f'tech+obs_dist({obs_dist:.0f}pip)'
    else:
        sl, sl_label = _calc_sl(tech_point, direction, f_body)

    sl_pips = abs(entry - sl) / PIP
    if sl_pips < 1:
        return None

    # TP selection
    if obs is not None:
        _obs_buf      = r55 * 0.06 * PIP
        _swing_price  = obs - _obs_buf if direction == 'SELL' else obs + _obs_buf
        _obs_dist_pip = abs(_swing_price - tech_point) / PIP
        _f_pct2       = f_body / r55 * 100
        if _f_pct2 > 80 and _obs_dist_pip > f_body * 0.60:
            tp_sel = (
                tech_point + f_body * 0.45 * PIP if direction == 'BUY'
                else tech_point - f_body * 0.45 * PIP
            )
            tp_lbl = 'TP 45% (พ่อ>80%R55)'
        else:
            tp_sel = obs
            tp_lbl = 'TP_adj (ก่ออุปสรรค)'
    else:
        tp_sel = tp3
        tp_lbl = 'TP3 (75% พ่อ)'

    # Direction-aware spread buffer (mirror Mountain v67)
    # BUY: tp_order ต่ำกว่า tp_sel (placed earlier so bid ≥ tp_order triggers fill)
    # SELL: tp_order สูงกว่า tp_sel (placed earlier so ask ≤ tp_order triggers fill)
    sign     = 1 if direction == 'BUY' else -1
    tp_order = tp_sel - sign * _TP_ORD_BUF
    tp_ref   = tp_sel - sign * _TP_REF_BUF

    # R:R ใช้ tp_ref (intent ใกล้จริงหลังหัก spread เล็กน้อย)
    reward_pip = abs(tp_ref - entry) / PIP
    rr         = reward_pip / sl_pips if sl_pips > 0 else 0.0
    lot        = _calc_lot(portfolio, sl_pips)
    if 20 <= m_pct <= 30:
        lot = round(lot / 2, 2)
    if f_body / r55 * 100 > 90:
        lot = round(lot * 2, 2)

    # Quality string ใช้ symbol set เดียวกับ Mountain — ตรงกับ signal_engine._parse_quality()
    # "✓"   → 1.0 (ผ่าน G2 quality threshold)
    # "~60%⚠️" → 0.6 (ผ่าน G2 ของผ่านขั้นต่ำ 0.5)
    quality = "✓" if m_pct <= 20 else "~60%⚠️"

    bar_num = lambda i: bars[i].bar_num if bars[i].bar_num else i + 1

    return Signal(
        pattern    = PATTERN_NAME,
        direction  = direction,
        quality    = quality,
        entry      = entry,
        sl         = sl,
        sl_name    = 'SL_MR',
        tp_order   = tp_order,
        tp_ref     = tp_ref,
        tp_name    = tp_lbl,
        rr         = rr,
        risk_pip   = sl_pips,
        reward_pip = reward_pip,
        lot        = lot,
        R55        = r55,
        details    = {
            'father_start': f_start, 'father_end': f_end, 'father_bars': f_end - f_start + 1,
            'father_body_pips': f_body, 'father_pct_r55': f_body / r55 * 100,
            'mother_idx': mother_idx, 'mother_body_pips': m_body,
            'mother_pct_father': m_pct, 'mother_quality': m_quality,
            'tech_point': tech_point, 'buffer_pips': buffer_pips,
            'entry_rule': entry_rule, 'sl_label': sl_label,
            'tp1': tp1, 'tp2': tp2, 'tp3': tp3,
            'obstacle': obs, 'obstacle_label': obs_label,
            'trend': trend,
            # swing_bar_nums: tracked here in details (Signal class doesn't expose this field)
            'swing_bar_nums': {bar_num(f_start), bar_num(f_end), bar_num(mother_idx)},
        },
    )


# ════════════════════════════════════════════════════════════════
# Public API — ตรงรูปแบบกับ xauusd_signal.find_signal
# ════════════════════════════════════════════════════════════════

def find_signal(bars: List[OHLC], portfolio: float = 1000.0) -> Optional[Signal]:
    """
    หาสัญญาณ MAI_RUAY ที่แท่งสุดท้าย (bars[-1]) เท่านั้น

    Returns: Signal หรือ None
    """
    if len(bars) < RANGE_WINDOW:
        return None

    # assign bar_num ถ้ายังไม่มี
    for i, b in enumerate(bars):
        if b.bar_num == 0:
            b.bar_num = i + 1

    return _analyze_bar(bars, len(bars) - 1, portfolio)
