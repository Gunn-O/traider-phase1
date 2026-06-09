"""
MAI_RUAY v2.04 — Father/Mother (Basic Father V2.04 M1)

Port ของ engine จาก notebook `strategy/Mairuay_Basic_Father_V2.04_M1.md`
Source of truth = engine code ใน cell 1 ของ notebook.

ความต่างจาก v1 (mai_ruay.py เดิม):
  - Father: 1-10 แท่ง สีเดียวห้ามแทรก, body รวม >60%R55, แต่ละแท่ง >4%R55
    (อนุโลม 2 แท่ง ≤3%R55 ถ้าเสียงข้างมาก >10%R55), Volatility Ratio > 1
  - Father R2: 1-8 แท่ง, body รวม >35%R55, อนุโลมแทรก 1 ตัว ≤10%R55
  - Mother: 3-25% ของ R55 (เปลี่ยน reference จาก % ของพ่อ)
  - 3 จุดเข้าพร้อมกัน: [market/mid_แม่, tech, tech±10%พ่อ] — split lot/3
  - SL = 40% × father_body (ตายตัว — ไม่ใช้ obstacle scanner)
  - TP = 45% × father_body (ตายตัว)
  - TP30/SL45 special: 50 แท่งก่อนพ่อ no-touch level
  - TP < 200 pip → skip
  - Round 2: หลัง SL → ภายใน 16 แท่ง ลอง R2 (ทิศเดิม)
  - ไม่มี anti-trend filter
  - ไม่มี obstacle scanner
  - ไม่มี spread buffer (TP_ORD_BUF/TP_REF_BUF)
  - R55 anchor = bar_idx - 1 (จบแท่งแม่)
"""
from __future__ import annotations
from typing import Optional, List, Tuple
import logging

from utils.xauusd_signal import OHLC, Signal, EntryPoint

logger = logging.getLogger(__name__)

PATTERN_NAME = "MAI_RUAY_M1"

# ─── Constants (ตรงกับ notebook v2.04) ─────────────────────────────
PIP           = 0.01
RANGE_WINDOW  = 55
MAX_FATHER    = 8       # R2 ใช้
RISK_PCT      = 0.10
PENDING_BARS  = 5       # LIMIT entries รอ 5 แท่ง


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


# ════════════════════════════════════════════════════════════════
# Father detection — Pass 1 (สีเดียวห้ามแทรก)
# ════════════════════════════════════════════════════════════════

def _find_father(
    bars: List[OHLC], father_end: int, r55: float
) -> Optional[Tuple[int, int, str, float, str]]:
    """
    หาแท่งพ่อ — Pass 1
    สีเดียวกัน 1-10 แท่ง, body รวม >60%R55, แต่ละแท่ง >4%R55
    ห้ามแทรกสีตรงข้าม, หยุดเมื่อเจอ Doji (body ≤ 2%R55), Vol Ratio >1
    คืน (start_idx, end_idx, direction, total_body_pips, pass_label) หรือ None
    """
    if father_end < 0 or father_end >= len(bars):
        return None
    eb = bars[father_end]
    if   _is_bull(eb): run_dir = 'UP'
    elif _is_bear(eb): run_dir = 'DOWN'
    else: return None

    # แท่งถัดไป (แม่) ต้องสวนทิศ
    if father_end + 1 < len(bars):
        nb = bars[father_end + 1]
        if (run_dir == 'UP'   and not _is_bear(nb)) or \
           (run_dir == 'DOWN' and not _is_bull(nb)):
            return None

    # สแกนสีเดียว 1-10 แท่ง ห้ามแทรก + หยุดที่ Doji (≤2%R55)
    run_start = father_end
    for k in range(father_end - 1, max(-1, father_end - 10), -1):
        b = bars[k]
        same = (run_dir == 'UP' and _is_bull(b)) or (run_dir == 'DOWN' and _is_bear(b))
        if same and _body_pips(b) > r55 * 0.02:
            run_start = k
        else:
            break

    length = father_end - run_start + 1
    if length < 1:
        return None

    f_start    = run_start
    span_open  = bars[f_start].open
    span_close = bars[father_end].close
    total_body = abs(span_open - span_close) / PIP
    pct        = total_body / r55 * 100 if r55 > 0 else 0

    # body รวม > 60%R55
    if pct <= 60:
        return None

    # แต่ละแท่ง body > 4%R55
    # อนุโลม: ถ้าเสียงข้างมาก >10%R55 → อนุโลม 2 แท่ง (>2% แต่ ≤3%)
    _big_count = sum(
        1 for idx in range(f_start, father_end + 1)
        if _body_pips(bars[idx]) > r55 * 0.10
    )
    _big_majority = _big_count > length / 2
    _fail_count = 0
    for idx in range(f_start, father_end + 1):
        _bp = _body_pips(bars[idx])
        if _bp <= r55 * 0.04:
            if _big_majority and _bp > r55 * 0.02:
                _fail_count += 1
            else:
                return None
    if _fail_count > 2:
        return None

    # Volatility Ratio > 1 (father avg body ÷ avg body 20 แท่งก่อน)
    _f_avg_body = total_body / length
    _pre20_start = max(0, f_start - 20)
    _pre20 = bars[_pre20_start:f_start]
    if len(_pre20) > 0:
        _pre20_avg = sum(_body_pips(b) for b in _pre20) / len(_pre20)
        _vol_ratio = _f_avg_body / _pre20_avg if _pre20_avg > 0 else 0.0
    else:
        _vol_ratio = 0.0
    if _vol_ratio <= 1:
        return None

    return (f_start, father_end, run_dir, total_body, 'Pass1 สีเดียว 1-10แท่ง >60%R55')


# ════════════════════════════════════════════════════════════════
# Father detection — Pass 2 / R2 (ไม้รวยรอบ 2)
# ════════════════════════════════════════════════════════════════

def _find_father_r2(
    bars: List[OHLC], father_end: int, r55: float
) -> Optional[Tuple[int, int, str, float, str]]:
    """
    Round 2: พ่อ 1-8 แท่ง สีเดียว >35%R55
    อนุญาตแทรก 1 ตัว body ≤10%R55 + ต่อจากแทรก close ต้องกลับมาตามทิศ
    แต่ละแท่ง body > 6%R55 (อนุโลม 1 แท่ง + ยกเว้นแทรก, แท่งสุดท้ายใช้ >4%)
    """
    if father_end < 0 or father_end >= len(bars):
        return None
    eb = bars[father_end]
    if   _is_bull(eb): run_dir = 'UP'
    elif _is_bear(eb): run_dir = 'DOWN'
    else: return None
    if father_end + 1 < len(bars):
        nb = bars[father_end + 1]
        if (run_dir == 'UP'   and not _is_bear(nb)) or \
           (run_dir == 'DOWN' and not _is_bull(nb)):
            return None

    # สแกนย้อนหลัง อนุญาตแทรก 1 ตัว
    run_start = father_end
    opp_count = 0
    opp_bar_k = -1
    for k in range(father_end - 1, max(-1, father_end - MAX_FATHER), -1):
        b = bars[k]
        same = (run_dir == 'UP' and _is_bull(b)) or (run_dir == 'DOWN' and _is_bear(b))
        if same:
            run_start = k
        else:
            if opp_count < 1:
                opp_count = 1
                opp_bar_k = k
                run_start = k
            else:
                break

    length = father_end - run_start + 1
    if length < 1:
        return None

    total_body = abs(bars[run_start].open - bars[father_end].close) / PIP
    pct        = total_body / r55 * 100 if r55 > 0 else 0
    if pct <= 35:
        return None

    # ตรวจแท่งแทรก (ถ้ามี)
    if opp_count == 1:
        if _body_pips(bars[opp_bar_k]) > r55 * 0.10:
            return None
        # แท่งต่อจากแทรก close ต้องกลับมาตามทิศ
        if opp_bar_k + 1 <= father_end:
            _next = bars[opp_bar_k + 1]
            _opp  = bars[opp_bar_k]
            if run_dir == 'UP'   and _next.close <= _opp.open: return None
            if run_dir == 'DOWN' and _next.close >= _opp.open: return None

    # แต่ละแท่ง body > 6%R55 (อนุโลม 1, ยกเว้นแทรก, แท่งสุดท้ายใช้ >4%)
    _fail6 = 0
    for _bi in range(run_start, father_end + 1):
        if opp_count == 1 and _bi == opp_bar_k:
            continue
        _min_thresh = r55 * 0.04 if _bi == father_end else r55 * 0.06
        if _body_pips(bars[_bi]) <= _min_thresh:
            _fail6 += 1
    if _fail6 > 1:
        return None

    return (run_start, father_end, run_dir, total_body, 'R2 ไม้รวยรอบ2')


# ════════════════════════════════════════════════════════════════
# Mother detection
# ════════════════════════════════════════════════════════════════

def _validate_mother(
    bars: List[OHLC], mother_idx: int, father_dir: str, r55: float, min_pct: float = 2.0
) -> Optional[Tuple[float, float, str]]:
    """
    แท่งแม่: สวนทิศพ่อ, body 3-25% **ของ R55** (เปลี่ยน reference จาก v1)
    min_pct: ค่าขั้นต่ำ (notebook ใช้ 2.0 ทั้ง R1+R2)
    คืน (mother_body_pips, mother_pct_r55, quality_label) หรือ None
    """
    if mother_idx < 0 or mother_idx >= len(bars):
        return None
    m = bars[mother_idx]
    m_body = _body_pips(m)
    if father_dir == 'UP'   and not _is_bear(m): return None
    if father_dir == 'DOWN' and not _is_bull(m): return None
    if r55 <= 0:
        return None
    pct = m_body / r55 * 100
    if pct < min_pct or pct > 25:
        return None
    quality = "สวยที่สุด ✅✅" if pct <= 10 else "ใช้ได้ ✅"
    return (m_body, pct, quality)


# ════════════════════════════════════════════════════════════════
# SL / TP helpers
# ════════════════════════════════════════════════════════════════

def _calc_tp_candidates(tech: float, father_body_pips: float, direction: str) -> Tuple[float, float, float]:
    """TP1=33%, TP2=50%, TP3=75% ของพ่อ — สำหรับ details/debug เท่านั้น (v2 ใช้ TP=45% ตายตัว)"""
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
    round2_info: Optional[dict] = None,
    debug: Optional[dict] = None,
) -> Optional[Signal]:
    """
    โครงสร้าง: [...][พ่อ 1-10 แท่ง][แม่ 1 แท่ง][ลูก=bar_idx]

    round2_info: {'tech': float, 'f_open_r1': float, 'entry_bar': int, 'direction': str}
                 ถ้าให้มา → ใช้ find_father_r2 + TP/SL จาก "พ่อรวม"
    debug: optional dict — เก็บ skip reason สำหรับ Tier 2
    """
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

    # 1. Range55 — anchor ที่จบแท่งแม่ (ตาม notebook v2.04)
    r55 = _calc_range55(bars, bar_idx - 1)
    if r55 <= 0:
        return _skip("R55 <= 0")

    # 2. แท่งพ่อ — Pass 1 หรือ R2
    if round2_info:
        fr = _find_father_r2(bars, father_end, r55)
    else:
        fr = _find_father(bars, father_end, r55)
    if fr is None:
        return _skip("ไม่เจอ father (Pass1: 1-10 สีเดียว >60%R55 / R2: >35%R55)")
    f_start, f_end, f_dir, f_body, f_pass = fr

    # Notebook spec (analyze_bar:428-430): พ่อ R2 เริ่มต้องอยู่ใน 6 แท่งจาก
    # child bar R1. signal_engine passes `bar_offset_in_window` — the index of
    # the R1 child bar inside the CURRENT slide window (recomputed every cycle
    # as curr_bar_idx - r1_bars_elapsed). The 16-bar outer limit is enforced
    # separately by signal_engine via r1_bars_elapsed counter.
    if round2_info and 'bar_offset_in_window' in round2_info:
        _r1_offset = int(round2_info['bar_offset_in_window'])
        if (f_start - _r1_offset) > 6:
            return _skip(
                f"R2: f_start {f_start} เกิน 6 แท่งจาก R1 lookup {_r1_offset}"
            )

    # Volatility Ratio (สำหรับ details)
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

    # 3. แท่งแม่
    _min_m_pct = 2.0  # ตาม notebook (ทั้ง R1 + R2)
    mr = _validate_mother(bars, mother_idx, f_dir, r55, min_pct=_min_m_pct)
    if mr is None:
        return _skip("mother ไม่ผ่าน (สวนทิศ + body 2-25% ของ R55)")
    m_body, m_pct, m_quality = mr

    # 4. ทิศทาง (v2: ไม่มี anti-trend filter)
    direction = 'BUY' if f_dir == 'DOWN' else 'SELL'

    # 5. Entry — tech_point + buffer
    m_row        = bars[mother_idx]
    father_close = bars[f_end].close
    mother_open  = m_row.open
    mother_close = m_row.close
    tech_point   = (father_close + mother_open) / 2
    buffer_pips  = min(100.0, f_body * 0.05)  # ไม่ได้ใช้ใน v2 (กันไว้ใน details)

    # 6. 3 จุดเข้า + ตรวจ child bar
    mid_mother = (mother_open + mother_close) / 2
    _e3_offset = f_body * 0.10 * PIP  # 10% พ่อ
    _e_tech    = tech_point
    _e_far     = tech_point - _e3_offset if direction == 'BUY' else tech_point + _e3_offset

    # Notebook v2.04 Bugfix1 (analyze_bar:426): 2-way bucket only.
    # m_pct ∈ [2, 10)  → ไม้1 MARKET (child.open) — Bugfix1 lowered the lower
    #                    bound from 3 to 2 so very-thin mothers (m_pct 2-3%)
    #                    enter via MARKET like the rest of the thin-mother
    #                    bucket, instead of falling into the else branch and
    #                    waiting at mid_แม่ as a LIMIT (which usually never
    #                    fills because price gaps past it on a thin mother).
    # otherwise        → ไม้1 LIMIT mid_แม่  (covers m_pct ≥ 10 and m_pct < 2,
    #                    but validate_mother rejects m_pct < 2 so in practice
    #                    only the 10-25% bucket reaches this branch).
    if 2 <= m_pct < 10:
        _e1       = bars[bar_idx].open
        _e1_label = 'จุด1:market(open_child)'
        _e1_is_market = True
    else:
        _e1       = mid_mother
        _e1_label = 'จุด1:mid_แม่'
        _e1_is_market = False

    _e2 = _e_tech
    _e3 = _e_far
    _e2_label = 'จุด2:tech_point'
    _e3_label = 'จุด3:tech±10%พ่อ'

    # entry หลัก = จุดแรก (ใช้ใน TP/SL/Lot calculation)
    entry      = _e1
    entry_rule = f"แม่ {m_pct:.1f}% → 3 จุดเข้า"

    # 7. TP candidates (สำหรับ details)
    tp1, tp2, tp3 = _calc_tp_candidates(tech_point, f_body, direction)

    # 8. SL = 40% × father_body (R1) — ตายตัว ไม่ใช้ obstacle scanner
    _sl_offset = f_body * 0.40 * PIP
    if direction == 'BUY':
        sl = tech_point - _sl_offset
    else:
        sl = tech_point + _sl_offset
    sl_label = f'SL 40%พ่อ ({f_body*0.40:.0f}pip)'
    sl_pips  = abs(entry - sl) / PIP
    if sl_pips < 1:
        return _skip(f"SL pip {sl_pips:.1f} < 1")

    # 9. TP = 45% × father_body (R1) — ตายตัว
    _tp_offset = f_body * 0.45 * PIP
    if direction == 'BUY':
        tp_sel = tech_point + _tp_offset
    else:
        tp_sel = tech_point - _tp_offset
    tp_lbl = f'TP 45%พ่อ ({f_body*0.45:.0f}pip)'

    # ── Round 2: TP/SL จาก "พ่อรวม" (R1 open → R2 close) ──
    if round2_info:
        _f_open_r1  = round2_info['f_open_r1']
        _f_close_r2 = bars[f_end].close
        _combined   = abs(_f_open_r1 - _f_close_r2) / PIP
        if direction == 'BUY':
            tp_sel = tech_point + _combined * 0.45 * PIP
            sl     = tech_point - _combined * 0.30 * PIP
        else:
            tp_sel = tech_point - _combined * 0.45 * PIP
            sl     = tech_point + _combined * 0.30 * PIP
        tp_lbl   = f'TP R2 45%พ่อรวม ({_combined*0.45:.0f}pip)'
        sl_label = f'SL R2 30%พ่อรวม ({_combined*0.30:.0f}pip)'
        sl_pips  = abs(entry - sl) / PIP

    # 10. TP30%/SL45% special: 50 แท่งก่อนพ่อ no-touch level (R1 เท่านั้น)
    if not round2_info:
        _pre50_start = max(0, f_start - 50)
        _pre50       = bars[_pre50_start:f_start]
        _r55_start_w = max(0, bar_idx - RANGE_WINDOW)
        _r55_window  = bars[_r55_start_w:bar_idx]
        if _r55_window and _pre50:
            _low55  = min(b.low for b in _r55_window)
            _high55 = max(b.high for b in _r55_window)
            _level60 = _low55  + r55 * 0.60 * PIP
            _level40 = _low55  + r55 * 0.40 * PIP
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
                tp_lbl   = ('TP 30% (50แท่งก่อนพ่อ ไม่มี Low<60%R55)' if direction == 'BUY'
                            else 'TP 30% (50แท่งก่อนพ่อ ไม่มี High>40%R55)')
                sl_label = f'SL 45%พ่อ ({f_body*0.45:.0f}pip)'
                sl_pips  = abs(entry - sl) / PIP

    # 11. TP filter: < 200 pip → skip
    tp_pips = abs(tp_sel - entry) / PIP
    if tp_pips < 200:
        return _skip(f"TP {tp_pips:.0f} pip < 200")

    rr  = tp_pips / sl_pips if sl_pips > 0 else 0.0
    lot = _calc_lot(portfolio, sl_pips)
    # แม่ 17-25% → lot / 2
    if 17 <= m_pct <= 25:
        lot = round(lot / 2, 2)
    # พ่อ > 90% R55 → lot × 2
    if f_body / r55 * 100 > 90:
        lot = round(lot * 2, 2)

    # 12. สร้าง 3 entries (split lot/3) + TP per-entry adjustment
    # Notebook spec (run_backtest): ถ้า TP_dist >= SL_dist → ใช้ TP เดิม
    #                                ถ้า TP_dist < SL_dist  → TP = entry ± SL_dist (RR=1.0)
    # SL ของทุก entry = sl เดียวกัน (วัดจาก tech_point)
    _lot_each = round(lot / 3, 2) if lot > 0 else 0.0

    def _adj_tp_for_entry(ep_price: float) -> float:
        _sl_dist = abs(ep_price - sl)
        _base_tp_dist = abs(tp_sel - ep_price)
        if _base_tp_dist >= _sl_dist:
            return tp_sel
        # เสียเปรียบ — RR ปกติ = 1.0
        return ep_price + _sl_dist if direction == 'BUY' else ep_price - _sl_dist

    entries = []
    for _ep, _label, _is_mkt in [
        (_e1, _e1_label, _e1_is_market),
        (_e2, _e2_label, False),
        (_e3, _e3_label, False),
    ]:
        entries.append(EntryPoint(
            price     = _ep,
            label     = _label,
            lot       = _lot_each,
            is_market = _is_mkt,
            tp        = _adj_tp_for_entry(_ep),
            sl        = sl,
        ))

    bar_num = lambda i: bars[i].bar_num if bars[i].bar_num else i + 1

    return Signal(
        pattern    = PATTERN_NAME,
        direction  = direction,
        # Quality string ใช้ symbol set เดียวกับ Mountain — ตรงกับ signal_engine._parse_quality()
        # "✓" → 1.0 / "~60%⚠️" → 0.6
        quality    = "✓" if m_pct <= 10 else "~60%⚠️",
        entry      = entry,
        sl         = sl,
        sl_name    = 'SL_MR_V2',
        # v2 ไม่มี spread buffer — tp_order = tp_ref = tp_sel
        tp_order   = tp_sel,
        tp_ref     = tp_sel,
        tp_name    = tp_lbl,
        rr         = rr,
        risk_pip   = sl_pips,
        reward_pip = tp_pips,
        lot        = lot,
        R55        = r55,
        # ── MaiRuay v2 fields ───────────────────────────────
        entries     = entries,
        is_round2   = bool(round2_info),
        father_pass = f_pass,
        vol_ratio   = _vol_ratio,
        details    = {
            'father_start': f_start, 'father_end': f_end,
            'father_bars': f_end - f_start + 1,
            'father_body_pips': f_body, 'father_pct_r55': f_body / r55 * 100,
            'father_first_pct': round(_f_first_pct, 1),
            'mother_idx': mother_idx, 'mother_body_pips': m_body,
            'mother_pct_r55': m_pct, 'mother_quality': m_quality,
            'tech_point': tech_point, 'buffer_pips': buffer_pips,
            'entry_rule': entry_rule, 'sl_label': sl_label,
            'tp1': tp1, 'tp2': tp2, 'tp3': tp3,
            # main.py reads details['order_type'] to decide MARKET vs LIMIT for
            # the FIRST entry. The 3-entries list carries per-entry is_market
            # flags for the multi-entry executor.
            'order_type': 'MARKET' if _e1_is_market else 'LIMIT',
            # Pending expiry in bars (notebook spec: 5 bars for limit entries)
            'pending_bars': PENDING_BARS,
            # TP-cancel buffer for pending limits (10% R55 — ตาม notebook)
            'tp_cancel_buffer_pips': r55 * 0.10,
            'swing_bar_nums': {bar_num(f_start), bar_num(f_end), bar_num(mother_idx)},
        },
    )


# ════════════════════════════════════════════════════════════════
# Public API — ตรงรูปแบบกับ xauusd_signal.find_signal
# ════════════════════════════════════════════════════════════════

def find_signal(
    bars: List[OHLC],
    portfolio: float = 1000.0,
    round2_info: Optional[dict] = None,
    debug: Optional[dict] = None,
) -> Optional[Signal]:
    """
    หาสัญญาณ MAI_RUAY v2.04 ที่แท่งสุดท้าย (bars[-1]) เท่านั้น

    round2_info: {'tech', 'f_open_r1', 'entry_bar', 'direction'}
                 ถ้าให้มา → ใช้ Pass 2 / R2 logic (ทิศต้องตรงกับ R1)
    debug: optional dict — ถ้าให้มาจะเก็บ skip reason สำหรับ Tier 2.
    Returns: Signal หรือ None
    """
    if len(bars) < RANGE_WINDOW:
        if debug is not None:
            debug['skip'] = f"bars {len(bars)} < {RANGE_WINDOW}"
        return None

    # assign bar_num ถ้ายังไม่มี
    for i, b in enumerate(bars):
        if b.bar_num == 0:
            b.bar_num = i + 1

    sig = _analyze_bar(bars, len(bars) - 1, portfolio, round2_info=round2_info, debug=debug)

    # R2 wrapper: ทิศต้องตรงกับ R1
    if sig is not None and round2_info and sig.direction != round2_info['direction']:
        if debug is not None:
            debug['skip'] = f"R2 direction {sig.direction} ≠ R1 direction {round2_info['direction']}"
        return None

    return sig
