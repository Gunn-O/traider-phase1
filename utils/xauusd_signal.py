"""
XAUUSD Signal Finder — v4.25
ระบบหาจุด Entry / SL / TP สำหรับ XAUUSD M5

Patterns ที่รองรับ:
  1. เทรนด์ขึ้น Impulse  → BUY  (Branch A)
  2. เทรนด์ลง Impulse    → SELL (Branch B)
  3. ภูเขา              → BUY  (Branch D) รวม รอบ 2

V4.25 Changes:
  - เพิ่ม impulse verification (3+ consecutive candles, 50% R55 total)
  - Pattern names: DOWNTREND_IMPULSE, UPTREND_IMPULSE
  - Matches TradingView backtest: 62.1% WR, 42 trades

การใช้งาน:
  from xauusd_signal import find_signal, OHLC
  bars = [OHLC(time, open, high, low, close), ...]
  result = find_signal(bars, portfolio=1000)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from swing_v414 import scan_swings


# ═══════════════════════════════════════════════════════════════════
# Data Types
# ═══════════════════════════════════════════════════════════════════

@dataclass
class OHLC:
    time:  str
    open:  float
    high:  float
    low:   float
    close: float
    bar_num: int = 0  # ถ้าไม่ระบุ จะถูก assign ตาม index

    @property
    def body_hi(self): return max(self.open, self.close)
    @property
    def body_lo(self): return min(self.open, self.close)
    @property
    def body_size(self): return (self.body_hi - self.body_lo) * 100  # pip

    def to_tuple(self):
        """แปลงเป็ tuple สำหรับ swing_v414"""
        return (self.bar_num, self.time, self.open, self.high, self.low, self.close)


@dataclass
class Signal:
    pattern:    str           # 'DOWNTREND_IMPULSE' | 'UPTREND_IMPULSE' | 'MOUNTAIN' | 'MOUNTAIN_R2'
    direction:  str           # 'BUY' | 'SELL'
    quality:    str           # '100%✓' | '~60%⚠️'
    entry:      float
    sl:         float
    sl_name:    str           # 'SL1' | 'SL2' | 'SL3' | 'SL3.5'
    tp_order:   float         # ราคาวาง order จริง
    tp_ref:     float         # ราคาใช้ตรวจ R:R
    tp_name:    str           # 'TP1' | 'TP2' | 'TP3'
    rr:         float
    risk_pip:   float
    reward_pip: float
    lot:        float = 0.0
    R55:        float = 0.0
    details:    dict  = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

_TP3_REF_BUF  =  0.10   # 10pip
_TP3_ORD_BUF  =  0.60   # 60pip  (spread buffer)
_BUF100       =  1.00   # 100pip
_CROSS_BUF    =  1.00   # ±100pip สำหรับตรวจการข้าม

def _q(pct: float) -> str:
    return "100%✓" if pct < 30 else "~60%⚠️" if pct < 50 else "✗"

def _bars_to_tuples(bars: list[OHLC]) -> list[tuple]:
    out = []
    for i, b in enumerate(bars):
        bn = b.bar_num if b.bar_num else i + 1
        out.append((bn, b.time, b.open, b.high, b.low, b.close))
    return out

def _O(t): return t[2]
def _H(t): return t[3]
def _L(t): return t[4]
def _C(t): return t[5]


def _pick_tp(entry: float, tps: list[tuple], sl: float, direction: str) -> tuple:
    """
    เลือก TP ที่ R:R ใกล้เคียง 1.0 ที่สุด ใช่ไม่ต่อยกว่า 1.0
    direction: 'BUY' หรือ 'SELL'
    tps: list of (tp_ref, tp_order, tp_name)
    คืน (tp_ref, tp_order, tp_name, rr) ของ TP ที่เลือก
    """
    risk = abs(entry - sl) * 100
    if risk <= 0:
        return None

    best = None
    for tp_ref, tp_ord, tp_name in tps:
        reward = abs(entry - tp_ref) * 100
        rr = reward / risk
        if rr >= 1.0:
            if best is None or rr < best[3]:   # เก็บ 1 ที่สุด
                best = (tp_ref, tp_ord, tp_name, rr)

    return best  # (tp_ref, tp_order, tp_name, rr) หรือ None


def _calc_lot(risk_pip: float, portfolio: float) -> float:
    """Lot = (portfolio × 10%) ÷ risk_pip"""
    if risk_pip <= 0:
        return 0.0
    return round((portfolio * 0.10) / risk_pip, 2)


# ═══════════════════════════════════════════════════════════════════
# SL Calculators
# ═══════════════════════════════════════════════════════════════════

def _calc_sl_sell(tech: float, frame_tuples: list[tuple],
                  pre_tuples: list[tuple], R55: float) -> tuple[float, str]:
    """
    คำนวณ SL สำหรับ SELL (เทรนด์ลง)
    tech = body_hi ของ LH
    คืน (sl_price, sl_name)
    """
    p15 = R55 * 0.15 / 100
    p10 = R55 * 0.10 / 100
    p5  = R55 * 0.05 / 100
    buf = _CROSS_BUF

    sl1 = tech + p15
    max_h_frame = max(_H(b) for b in frame_tuples)

    # ① ไม่ก่อนเส้น → SL2
    if sl1 <= max_h_frame:
        sl2 = max_h_frame + p10
        cross2 = [b for b in pre_tuples if (_L(b) - buf) <= sl2 <= (_H(b) + buf)]
        if len(cross2) <= 1:
            return sl2, "SL2"
        mhc2 = max(_H(b) for b in cross2)
        return mhc2 + p10, "SL3"

    # ② ก่อนเส้น แต่การข้าย ≥2 แท่ง → SL3.5
    cross1 = [b for b in pre_tuples if (_L(b) - buf) <= sl1 <= (_H(b) + buf)]
    if len(cross1) >= 2:
        mhc1 = max(_H(b) for b in cross1)
        return mhc1 + p5, "SL3.5"

    return sl1, "SL1"


def _calc_sl_buy(tech: float, frame_tuples: list[tuple],
                 pre_tuples: list[tuple], R55: float) -> tuple[float, str]:
    """
    คำนวณ SL สำหรับ BUY (เทรนด์ขึ้น)
    tech = body_lo ของ HL
    คืน (sl_price, sl_name)
    """
    p15 = R55 * 0.15 / 100
    p10 = R55 * 0.10 / 100
    p5  = R55 * 0.05 / 100
    buf = _CROSS_BUF

    sl1 = tech - p15
    min_l_frame = min(_L(b) for b in frame_tuples)

    # ① ไม่ก่อนเส้น → SL2
    if sl1 >= min_l_frame:
        sl2 = min_l_frame - p10
        cross2 = [b for b in pre_tuples if (_L(b) - buf) <= sl2 <= (_H(b) + buf)]
        if len(cross2) <= 1:
            return sl2, "SL2"
        mlc2 = min(_L(b) for b in cross2)
        return mlc2 - p10, "SL3"

    # ② ก่อนเส้น แต่การข้าย ≥2 แท่ง → SL3.5
    cross1 = [b for b in pre_tuples if (_L(b) - buf) <= sl1 <= (_H(b) + buf)]
    if len(cross1) >= 2:
        mlc1 = min(_L(b) for b in cross1)
        return mlc1 - p5, "SL3.5"

    return sl1, "SL1"


def _calc_sl_mountain(base_low: float, base_tuples: list[tuple],
                      pre_tuples: list[tuple], R55: float) -> tuple[float, str]:
    """
    SL สำหรับภูเขา
    SL1 = เส้นต่ำสุดในโต้งภาก − 15%R55
    ถ้าการข้าย ≥2 แท่ง → SL2
    คืน (sl_price, sl_name)
    """
    p15 = R55 * 0.15 / 100
    p10 = R55 * 0.10 / 100
    buf = _CROSS_BUF

    min_l_base = min(_L(b) for b in base_tuples)
    sl1 = min_l_base - p15
    cross1 = [b for b in pre_tuples if (_L(b) - buf) <= sl1 <= (_H(b) + buf)]
    if len(cross1) >= 2:
        mlc1 = min(_L(b) for b in cross1)
        return mlc1 - p10, "SL2"

    return sl1, "SL1"


def _verify_impulse(window_t: list[tuple], direction: str, R55: float) -> bool:
    """
    V4.25: ตรวจว่ามี impulse move ใน window

    เงื่อนไข:
    - หา consecutive candles ที่มี body ≥ 3% R55
    - direction 'SELL': bearish (Close < Open)
    - direction 'BUY':  bullish (Close > Open)
    - ต้องมีอย่างน้อย 3 แท่งต่อเนื่อง
    - รวม body ≥ 50% R55

    Note: Impulse can occur anywhere in window.
          Zone check applies to consolidation (LH/LL or HL/HH), not impulse.

    Args:
        window_t: 55 bars window (tuple format)
        direction: 'SELL' หรือ 'BUY'
        R55: Range 55 (pip)

    Returns:
        True ถ้าพบ impulse move, False ถ้าไม่พบ
    """
    if len(window_t) < 3:
        return False

    # Thresholds
    body_thresh  = R55 * 0.03 / 100   # 3% R55 ต่อแท่ง (USD)
    total_thresh = R55 * 0.50 / 100   # 50% R55 รวม (USD)
    min_bars     = 3

    # Loop through window to find consecutive impulse candles
    for i in range(len(window_t)):
        consecutive = 0
        total_body  = 0.0

        # Try to build consecutive run starting from i
        for j in range(i, min(i + 10, len(window_t))):
            bar = window_t[j]
            o, c = _O(bar), _C(bar)
            body = abs(c - o)

            # Check direction
            is_directional = (c < o) if direction == 'SELL' else (c > o)

            # Check if this bar qualifies
            if is_directional and body >= body_thresh:
                consecutive += 1
                total_body  += body

                # Check if we found impulse
                if consecutive >= min_bars and total_body >= total_thresh:
                    return True
            else:
                # Bar doesn't qualify → reset
                break

    return False


# ═══════════════════════════════════════════════════════════════════
# Pattern Detectors
# ═══════════════════════════════════════════════════════════════════

def _detect_downtrend(window_t: list[tuple], all_t: list[tuple],
                      R55: float, H55: float, L55: float,
                      cur: tuple) -> Optional[Signal]:
    """
    ตรวจเทรนด์ลง → SELL
    """
    # Pass 1: หา LH ล่าสุด สำหรับ zone_lo
    hs0, _ = scan_swings(window_t, R55)
    if len(hs0) < 2:
        return None
    lh_zone_lo = hs0[-1]['body_hi'] - _BUF100

    # Pass 2: สแกนพร้อม Right2 exception
    hs, ls = scan_swings(window_t, R55,
                         cur_H=_H(cur), lh_zone_lo=lh_zone_lo)
    if len(hs) < 2 or not ls:
        return None

    last_lh = hs[-1]
    last_ll = ls[-1]

    pct_lh = (last_lh['body_hi'] - L55) / (H55 - L55) * 100
    pct_ll = (last_ll['body_lo'] - L55) / (H55 - L55) * 100
    if pct_lh >= 50 or pct_ll >= 50:
        return None

    rb_pct = (last_lh['body_hi'] - last_ll['body_lo']) * 100 / R55 * 100
    if not (10 <= rb_pct <= 40):
        return None

    # V4.25: Impulse verification
    if not _verify_impulse(window_t, 'SELL', R55):
        return None

    lh_hi   = last_lh['body_hi']
    zone_lo = lh_hi - _BUF100
    if _H(cur) < zone_lo:
        return None

    entry = zone_lo

    # กรอบ LH → LL สำหรับ SL
    lh_b0 = last_lh['bar_nums'][0]
    ll_b1 = last_ll['bar_nums'][-1]
    bmin, bmax = min(lh_b0, ll_b1), max(lh_b0, ll_b1)
    frame_t = [b for b in all_t if bmin <= b[0] <= bmax] or \
              [b for b in all_t if b[0] in last_lh['bar_nums']]

    # เส้นก่อนหน้า frame สำหรับตรวจการข้าย
    fi = next((i for i, b in enumerate(all_t) if b[0] == frame_t[0][0]), 0)
    pre_t = all_t[max(0, fi - 30):fi]

    sl, sl_name = _calc_sl_sell(lh_hi, frame_t, pre_t, R55)
    risk = (sl - entry) * 100
    if risk <= 0:
        return None

    ll_ref = last_ll['body_lo']
    dist   = entry - ll_ref
    tp1    = entry - dist * 0.35
    tp2    = entry - dist * 0.50
    tp3r   = ll_ref + _TP3_REF_BUF
    tp3o   = ll_ref + _TP3_ORD_BUF

    picked = _pick_tp(entry, [(tp1, tp1, 'TP1'), (tp2, tp2, 'TP2'),
                               (tp3r, tp3o, 'TP3')], sl, 'SELL')
    if picked is None:
        # ยัน 2: ลด SL
        rw3 = (entry - tp3r) * 100
        sl_adj = entry + rw3 / 100
        picked = (tp3r, tp3o, 'TP3(adj)', rw3 / rw3)
        sl = sl_adj
        risk = rw3

    tp_ref, tp_ord, tp_name, rr = picked

    quality = "100%✓" if ("100%" in _q(pct_lh) and "100%" in _q(pct_ll)) else "~60%⚠️"

    return Signal(
        pattern   = 'DOWNTREND_IMPULSE',
        direction = 'SELL',
        quality   = quality,
        entry     = entry,
        sl        = sl,
        sl_name   = sl_name,
        tp_order  = tp_ord,
        tp_ref    = tp_ref,
        tp_name   = tp_name,
        rr        = rr,
        risk_pip  = abs(sl - entry) * 100,
        reward_pip= abs(entry - tp_ref) * 100,
        R55       = R55,
        details   = {
            'lh': last_lh, 'll': last_ll,
            'pct_lh': pct_lh, 'pct_ll': pct_ll,
            'rebound': rb_pct,
            'tp1': tp1, 'tp2': tp2, 'tp3_ref': tp3r,
        }
    )


def _detect_uptrend(window_t: list[tuple], all_t: list[tuple],
                    R55: float, H55: float, L55: float,
                    cur: tuple) -> Optional[Signal]:
    """
    ตรวจเทรนด์ขึ้น → BUY  (Mirror จากเทรนด์ลง)
    """
    # Pass 1: หา HL ล่าสุด
    _, ls0 = scan_swings(window_t, R55)
    if len(ls0) < 2:
        return None
    hl_zone_hi = ls0[-1]['body_lo'] + _BUF100

    # Pass 2: ตรพร้อม Right2 exception
    hs, ls = scan_swings(window_t, R55,
                         cur_L=_L(cur), hl_zone_hi=hl_zone_hi)
    if not hs or len(ls) < 2:
        return None

    last_hl = ls[-1]
    last_hh = hs[-1]

    pct_hl = (last_hl['body_lo'] - L55) / (H55 - L55) * 100
    pct_hh = (last_hh['body_hi'] - L55) / (H55 - L55) * 100
    if pct_hl < 50 or pct_hh < 50:
        return None

    rb_pct = (last_hh['body_hi'] - last_hl['body_lo']) * 100 / R55 * 100
    if not (10 <= rb_pct <= 40):
        return None

    # V4.25: Impulse verification
    if not _verify_impulse(window_t, 'BUY', R55):
        return None

    hl_lo   = last_hl['body_lo']
    zone_hi = hl_lo + _BUF100
    if _L(cur) > zone_hi:
        return None

    entry = zone_hi

    hh_b0 = last_hh['bar_nums'][0]
    hl_b1 = last_hl['bar_nums'][-1]
    bmin, bmax = min(hh_b0, hl_b1), max(hh_b0, hl_b1)
    frame_t = [b for b in all_t if bmin <= b[0] <= bmax] or \
              [b for b in all_t if b[0] in last_hl['bar_nums']]

    fi = next((i for i, b in enumerate(all_t) if b[0] == frame_t[0][0]), 0)
    pre_t = all_t[max(0, fi - 30):fi]

    sl, sl_name = _calc_sl_buy(hl_lo, frame_t, pre_t, R55)
    risk = (entry - sl) * 100
    if risk <= 0:
        return None

    hh_ref = last_hh['body_hi']
    dist   = hh_ref - entry
    tp1    = entry + dist * 0.35
    tp2    = entry + dist * 0.50
    tp3r   = hh_ref - _TP3_REF_BUF
    tp3o   = hh_ref - _TP3_ORD_BUF

    picked = _pick_tp(entry, [(tp1, tp1, 'TP1'), (tp2, tp2, 'TP2'),
                               (tp3r, tp3o, 'TP3')], sl, 'BUY')
    if picked is None:
        rw3 = (tp3r - entry) * 100
        sl_adj = entry - rw3 / 100
        picked = (tp3r, tp3o, 'TP3(adj)', 1.0)
        sl = sl_adj
        risk = rw3

    tp_ref, tp_ord, tp_name, rr = picked
    quality = "100%✓" if ("100%" in _q(100 - pct_hl) and "100%" in _q(100 - pct_hh)) else "~60%⚠️"

    return Signal(
        pattern   = 'UPTREND_IMPULSE',
        direction = 'BUY',
        quality   = quality,
        entry     = entry,
        sl        = sl,
        sl_name   = sl_name,
        tp_order  = tp_ord,
        tp_ref    = tp_ref,
        tp_name   = tp_name,
        rr        = rr,
        risk_pip  = abs(entry - sl) * 100,
        reward_pip= abs(tp_ref - entry) * 100,
        R55       = R55,
        details   = {
            'hl': last_hl, 'hh': last_hh,
            'pct_hl': pct_hl, 'pct_hh': pct_hh,
            'rebound': rb_pct,
            'tp1': tp1, 'tp2': tp2, 'tp3_ref': tp3r,
        }
    )


def _detect_mountain(window_t: list[tuple], all_t: list[tuple],
                     R55: float, cur: tuple,
                     prev_entry: Optional[float] = None,
                     prev_entry_bar: Optional[int] = None,
                     base_lo_r1: Optional[float] = None) -> Optional[Signal]:
    """
    ตรวจภูเขา → BUY
    prev_entry      = entry ของรอบ 1 (ถ้ามี → ตรวจรอบ 2)
    prev_entry_bar  = bar_num ที่ entry รอบ 1
    base_lo_r1      = body_lo งาน้ายต่าย รอบ 1 (สำหรับตรวจเงื่อนไขรอบ 2)
    """
    hs, ls = scan_swings(window_t, R55)
    if not hs or not ls:
        return None

    is_round2 = prev_entry is not None

    if not is_round2:
        # รอบ 1: ฐาน = LL ต่ำสุด, ยอด = SH ล่าสุดหลังฐาน
        base_sw = min(ls, key=lambda s: s['body_lo'])
    else:
        # รอบ 2: ฐานต่วา = SL ที่เกิดหลังยอดภูเขา (หลัง entry รอบ 1)
        # ต้อง body_lo ≥ base_lo_r1
        after_entry = [s for s in ls
                       if s['bar_nums'][0] > (prev_entry_bar or 0)
                       and s['body_lo'] >= (base_lo_r1 or 0)]
        if not after_entry:
            return None
        base_sw = min(after_entry, key=lambda s: s['body_lo'])

    peaks_after = [s for s in hs if s['bar_nums'][0] > base_sw['bar_nums'][-1]]
    if not peaks_after:
        return None
    peak_sw = max(peaks_after, key=lambda s: s['bar_nums'][0])

    base_lo = base_sw['body_lo']
    peak_hi = peak_sw['body_hi']
    height  = (peak_hi - base_lo) * 100

    if height < R55 * 0.50:
        return None
    # V65: เงื่อนไขเพิ่มเติม 4 ข้อ
    # 1. ขนาดภูเขา >= 10 แท่ง
    bars_base_to_peak = peak_sw['bar_nums'][0] - base_sw['bar_nums'][-1]
    bars_peak_to_cur = cur[0] - peak_sw['bar_nums'][-1]
    mountain_size = bars_base_to_peak + bars_peak_to_cur
    if mountain_size < 10:
        return None
    
    # 2. ห้ามมี Low ทะลุ thresh_10 ในช่วง 20-80% ของภูเขา
    thresh_10 = base_lo + (peak_hi - base_lo) * 0.20
    all_mid = [b for b in window_t
               if base_sw['bar_nums'][-1] < b[0] <= cur[0]]
    total_bars = len(all_mid)
    if total_bars >= 3:
        lo20 = int(total_bars * 0.20)
        hi80 = int(total_bars * 0.80)
        scan_bars = all_mid[lo20:hi80+1]
        for b in scan_bars:
            if _L(b) <= thresh_10:
                return None  # ราคาลงเทลุดเกินเกณฑ์ → ✗
    
    # 3. ฐาน→entry ไม่เกิน 42 แท่ง
    bars_base_to_cur = cur[0] - base_sw['bar_nums'][-1]
    if bars_base_to_cur > 42:
        return None
    
    # 4. ตรวจ Swing High ระหว่างฐาน → Entry Zone
    # ถ้าฐาน → entry ≤ 25 แท่ง → ข้าม SH check
    bars_base_to_entry = cur[0] - base_sw['bar_nums'][-1]
    if bars_base_to_entry > 25:
        peak_bar_last = peak_sw['bar_nums'][-1]
        sh_after_peak = [s for s in hs if s['bar_nums'][0] > peak_bar_last
                         and s['bar_nums'][0] <= cur[0]]
        if len(sh_after_peak) > 2:
            return None


    buf = min(height * 0.10, 100)
    zone_lo = base_lo - buf / 100
    zone_hi = base_lo + buf / 100

    if not (_L(cur) <= zone_hi and _H(cur) >= zone_lo):
        return None

    bars_since = cur[0] - peak_sw['bar_nums'][-1]

    entry = min(_H(cur), zone_hi)

    # โต้งภูเขา
    base_t = [b for b in window_t if b[0] in base_sw['bar_nums']]
    if not base_t:
        return None

    fi = next((i for i, b in enumerate(all_t) if b[0] == base_t[0][0]), 0)
    pre_t = all_t[max(0, fi - 30):fi]

    sl, sl_name = _calc_sl_mountain(base_lo, base_t, pre_t, R55)
    risk = (entry - sl) * 100
    if risk <= 0:
        return None

    if not is_round2:
        # รอบ 1: TP วัดจากความสูงภูเขา
        dist = peak_hi - base_lo
        tp1  = entry + dist / 3
        tp2  = entry + dist / 2
        tp3r = peak_hi - _TP3_REF_BUF
        tp3o = peak_hi - _TP3_ORD_BUF
        pattern_name = 'MOUNTAIN'
    else:
        # รอบ 2: TP วัดจาก body_hi สูงสุดหลัง entry รอบ 1
        after_r1 = [b for b in all_t if b[0] > (prev_entry_bar or 0)]
        if not after_r1:
            return None
        tp_ref_hi = max(_H(b) for b in after_r1)   # เท่าเส้น
        # หา body_hi สูงสุด (เงื่อนไขเทียบ)
        tp_ref_body = max(max(_O(b), _C(b)) for b in after_r1)
        tp_ref_base = tp_ref_body   # TP_ref = body_hi สูงสุด
        dist = tp_ref_base - entry
        tp1  = entry + dist / 3
        tp2  = entry + dist / 2
        tp3r = tp_ref_base - R55 * 0.05 / 100
        tp3o = tp_ref_base - R55 * 0.05 / 100 - _TP3_ORD_BUF + _TP3_REF_BUF
        pattern_name = 'MOUNTAIN_R2'

    picked = _pick_tp(entry, [(tp1, tp1, 'TP1'), (tp2, tp2, 'TP2'),
                               (tp3r, tp3o, 'TP3')], sl, 'BUY')
    if picked is None:
        rw3 = (tp3r - entry) * 100
        sl_adj = entry - rw3 / 100
        picked = (tp3r, tp3o, 'TP3(adj)', 1.0)
        sl = sl_adj
        risk = rw3

    tp_ref, tp_ord, tp_name, rr = picked

    return Signal(
        pattern   = pattern_name,
        direction = 'BUY',
        quality   = '✓' if bars_since <= 40 else '⚠️ ช้า',
        entry     = entry,
        sl        = sl,
        sl_name   = sl_name,
        tp_order  = tp_ord,
        tp_ref    = tp_ref,
        tp_name   = tp_name,
        rr        = rr,
        risk_pip  = abs(entry - sl) * 100,
        reward_pip= abs(tp_ref - entry) * 100,
        R55       = R55,
        details   = {
            'base': base_sw, 'peak': peak_sw,
            'base_lo': base_lo, 'peak_hi': peak_hi,
            'height': height, 'buf': buf,
            'zone_lo': zone_lo, 'zone_hi': zone_hi,
            'bars_since_peak': bars_since,
            'tp1': tp1, 'tp2': tp2, 'tp3_ref': tp3r,
        }
    )


# ═══════════════════════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════════════════════

def find_signal(
    bars:             list[OHLC],
    portfolio:        float = 1000.0,
    mountain_state:   Optional[dict] = None,
) -> Optional[Signal]:
    """
    หาสัญญาณ Entry จาก 55 แท่งล่าสุด

    Parameters:
        bars          : ข้อมูล OHLC เรียงจากเก่า→ใหม่ (ต้องมีอย่างน้อย 55 แท่ง)
        portfolio     : เงินทุน USD (ใช้คำนวณ Lot)
        mountain_state: dict สำหรับภูเขารอบ 2
                        {'prev_entry': float, 'prev_entry_bar': int,
                         'base_lo_r1': float, 'tp_bar': int}
                        (ส่งเข้ามาเมื่อ TP รอบ 1 เก็บแล้ว และยังอยู่ใน 40 แท่ง)

    Returns:
        Signal หรือ None ถ้าไม่มีสัญญาณ
    """
    if len(bars) < 55:
        return None

    # เก็บ 55 แท่งล่าสุด
    window = bars[-55:]
    cur_bar = window[-1]

    # Assign bar_num ถ้าไม่มี
    for i, b in enumerate(bars):
        if b.bar_num == 0:
            b.bar_num = i + 1

    window_t = _bars_to_tuples(window)
    all_t    = _bars_to_tuples(bars)
    cur_t    = window_t[-1]

    H55 = max(_H(b) for b in window_t)
    L55 = min(_L(b) for b in window_t)
    R55 = (H55 - L55) * 100

    if R55 == 0:
        return None

    # ══ ลำดับ Priority ══════════════════════════════════════════════
    # 1. ภูเขารอบ 2 (ถ้า state ส่งมา)
    if mountain_state:
        mst = mountain_state
        if (cur_t[0] - mst['tp_bar']) <= 40:
            sig = _detect_mountain(
                window_t, all_t, R55, cur_t,
                prev_entry     = mst['prev_entry'],
                prev_entry_bar = mst['prev_entry_bar'],
                base_lo_r1     = mst['base_lo_r1'],
            )
            if sig:
                sig.lot = _calc_lot(sig.risk_pip, portfolio)
                return sig

    # 2. ภูเขารอบ 1
    sig = _detect_mountain(window_t, all_t, R55, cur_t)
    if sig:
        sig.lot = _calc_lot(sig.risk_pip, portfolio)
        return sig

    # V65: MOUNTAIN-only — Downtrend/Uptrend disabled
    # # 3. เทรนด์ลง
    # sig = _detect_downtrend(window_t, all_t, R55, H55, L55, cur_t)
    # if sig:
    #     sig.lot = _calc_lot(sig.risk_pip, portfolio)
    #     return sig

    # # 4. เทรนด์ขึ้น
    # sig = _detect_uptrend(window_t, all_t, R55, H55, L55, cur_t)
    # if sig:
    #     sig.lot = _calc_lot(sig.risk_pip, portfolio)
    #     return sig

    return None


def format_signal(sig: Signal, cur_time: str = "") -> str:
    """จัดรูปเป็ output สวยงาม"""
    d = sig.direction
    arrow = "🟢" if d == "BUY" else "🔴"
    icon  = "🏔" if "MOUNTAIN" in sig.pattern else arrow

    lines = [
        f"{'═'*52}",
        f"{icon} {sig.pattern} → {d}  {sig.quality}  {cur_time}",
        f"{'═'*52}",
        f"R55      = {sig.R55:.0f} pip",
    ]

    det = sig.details
    if sig.pattern in ('MOUNTAIN', 'MOUNTAIN_R2'):
        lines += [
            f"ฐาน      = {det['base']['times'][0]}→{det['base']['times'][-1]}  {det['base_lo']:.3f}",
            f"ยอด      = {det['peak']['times'][0]}→{det['peak']['times'][-1]}  {det['peak_hi']:.3f}",
            f"ความสูง  = {det['height']:.0f}pip ({det['height']/sig.R55*100:.1f}%R55)  {det['bars_since_peak']} แท่งจากยอด",
        ]
    else:
        if 'lh' in det:
            lines += [
                f"LH       = {det['lh']['times'][0]}→{det['lh']['times'][-1]}  {det['lh']['body_hi']:.3f}  {det['pct_lh']:.1f}%",
                f"LL       = {det['ll']['times'][0]}→{det['ll']['times'][-1]}  {det['ll']['body_lo']:.3f}  {det['pct_ll']:.1f}%",
                f"Rebound  = {det['rebound']:.1f}%",
            ]
        elif 'hl' in det:
            lines += [
                f"HL       = {det['hl']['times'][0]}→{det['hl']['times'][-1]}  {det['hl']['body_lo']:.3f}  {det['pct_hl']:.1f}%",
                f"HH       = {det['hh']['times'][0]}→{det['hh']['times'][-1]}  {det['hh']['body_hi']:.3f}  {det['pct_hh']:.1f}%",
                f"Rebound  = {det['rebound']:.1f}%",
            ]

    lines += [
        f"{'═'*52}",
        f"Entry    = {sig.entry:.3f}",
        f"{sig.sl_name:<8} = {sig.sl:.3f}  ({sig.risk_pip:.0f} pip)",
        f"{'═'*52}",
    ]

    for tp_name, tp_val in [('TP1', det.get('tp1')), ('TP2', det.get('tp2')), ('TP3 ref', det.get('tp3_ref'))]:
        if tp_val is None:
            continue
        dist = abs(tp_val - sig.entry) * 100
        rr = dist / sig.risk_pip if sig.risk_pip else 0
        chosen = "← เลือก" if tp_name.replace(' ref','') == sig.tp_name.replace('(adj)','').strip() else ""
        lines.append(f"{tp_name:<8} = {tp_val:.3f}  ({dist:.0f}pip)  R:R={rr:.2f}  {chosen}")

    tp_ord_dist = abs(sig.tp_order - sig.entry) * 100
    lines += [
        f"TP order = {sig.tp_order:.3f}  ({tp_ord_dist:.0f}pip)  ← วาง order",
        f"{'═'*52}",
        f"R:R      = {sig.rr:.2f}",
        f"Lot      = {sig.lot:.2f}  (portfolio-based)",
        f"{'═'*52}",
    ]
    return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════
# XAUUSD Uptrend + Downtrend Scanner v3.4
# Ported from notebook XAUUSD_Uptrend_Downtrend_Scanner_v3.4.md
# These are ADDITIVE — no existing function above is modified.
# Public detectors:
#     _detect_uptrend_scanner(bars, portfolio)   -> Optional[Signal]
#     _detect_downtrend_scanner(bars, portfolio) -> Optional[Signal]
# ════════════════════════════════════════════════════════════════════

# ── Scanner constants (notebook v3.4) ─────────────────────────────
_SCAN_WINDOW          = 55
_SCAN_LOOKBACK        = 25
_SCAN_C1_MIN          = 0.60   # Close in upper 60% of R55
_SCAN_C2_MIN          = 0.55   # min Low of last 5 bars in upper 55% of R55
_SCAN_C3_MAX          = 0.30   # Close drop from HH ≤ 30% R55
_SCAN_C4_MIN          = 0.25   # 2-8 consecutive bullish body sum ≥ 25% R55
_SCAN_C5_MAX          = 0.30   # no bearish body > 30% R55 in lookback
_SCAN_C6_MAX_START    = 0.40   # max close in (lookback + first 5) ≤ L55 + 40% R55
_SCAN_C6_START_BARS   = 5
_SCAN_MIN_R55_USD     = 3.0    # skip flat windows
_SCAN_SL_MIN_BODY_PCT = 0.04   # swing pair must each have body > 4% R55
_SCAN_ZONE_UP_LO      = 0.65   # BUY entry zone bottom (% R55 above L55)
_SCAN_ZONE_UP_HI      = 0.85
_SCAN_ZONE_DOWN_LO    = 0.15   # SELL entry zone bottom (% R55 above L55)
_SCAN_ZONE_DOWN_HI    = 0.35
_SCAN_FATHER_MAX_BARS = 8
_SCAN_FATHER_MIN_PCT  = 40.0   # anti-trend kill threshold (% R55, pip basis)
_SCAN_FATHER_MAX_PCT  = 100.0


def _scan_lookback_tuples(bars: list, lookback_bars: int = _SCAN_LOOKBACK) -> list:
    """Last `lookback_bars` bars BEFORE the 55-bar window. Empty list if not enough history."""
    if len(bars) <= _SCAN_WINDOW:
        return []
    end = len(bars) - _SCAN_WINDOW
    start = max(0, end - lookback_bars)
    return _bars_to_tuples(bars[start:end])


# ── Uptrend criteria (return bool) ────────────────────────────────

def _scan_c1_up(window_t, L55, R55):
    return (_C(window_t[-1]) - L55) / R55 >= _SCAN_C1_MIN

def _scan_c2_up(window_t, L55, R55, n: int = 5):
    return (min(_L(b) for b in window_t[-n:]) - L55) / R55 >= _SCAN_C2_MIN

def _scan_c3_up(window_t, R55):
    H = max(_H(b) for b in window_t)
    return (H - _C(window_t[-1])) / R55 <= _SCAN_C3_MAX

def _scan_c4_up(window_t, R55):
    """Find any 2-8 consecutive bullish bars whose body sum ≥ C4_MIN × R55."""
    n = len(window_t)
    for start in range(n):
        bsum = 0.0
        cnt = 0
        for end in range(start, min(start + 8, n)):
            body = _C(window_t[end]) - _O(window_t[end])
            if body <= 0:
                break
            bsum += body
            cnt += 1
            if cnt >= 2 and (bsum / R55) >= _SCAN_C4_MIN:
                return True
    return False

def _scan_c5_up(lookback_t, R55):
    if not lookback_t or R55 <= 1e-6:
        return True
    for b in lookback_t:
        body = _O(b) - _C(b)            # bearish > 0
        if body > 0 and (body / R55) >= _SCAN_C5_MAX:
            return False
    return True

def _scan_c6_up(window_t, lookback_t, L55, R55):
    """Combined check: max close in (lookback + first 5 of window) must stay below
    L55 + C6_MAX_START × R55. This enforces 'starts low' for an uptrend."""
    level = L55 + _SCAN_C6_MAX_START * R55
    closes = [_C(b) for b in window_t[: _SCAN_C6_START_BARS]]
    if lookback_t:
        closes += [_C(b) for b in lookback_t]
    return (max(closes) <= level) if closes else True


# ── Downtrend criteria (mirror of uptrend) ────────────────────────

def _scan_c1_down(window_t, H55, R55):
    return (H55 - _C(window_t[-1])) / R55 >= _SCAN_C1_MIN

def _scan_c2_down(window_t, H55, R55, n: int = 5):
    return (H55 - max(_H(b) for b in window_t[-n:])) / R55 >= _SCAN_C2_MIN

def _scan_c3_down(window_t, R55):
    L = min(_L(b) for b in window_t)
    return (_C(window_t[-1]) - L) / R55 <= _SCAN_C3_MAX

def _scan_c4_down(window_t, R55):
    n = len(window_t)
    for start in range(n):
        bsum = 0.0
        cnt = 0
        for end in range(start, min(start + 8, n)):
            body = _O(window_t[end]) - _C(window_t[end])
            if body <= 0:
                break
            bsum += body
            cnt += 1
            if cnt >= 2 and (bsum / R55) >= _SCAN_C4_MIN:
                return True
    return False

def _scan_c5_down(lookback_t, R55):
    if not lookback_t or R55 <= 1e-6:
        return True
    for b in lookback_t:
        body = _C(b) - _O(b)            # bullish > 0
        if body > 0 and (body / R55) >= _SCAN_C5_MAX:
            return False
    return True

def _scan_c6_down(window_t, lookback_t, H55, R55):
    """Mirror of C6 — min close in (lookback + first 5) must stay ABOVE H55 - 40% R55."""
    level = H55 - _SCAN_C6_MAX_START * R55
    closes = [_C(b) for b in window_t[: _SCAN_C6_START_BARS]]
    if lookback_t:
        closes += [_C(b) for b in lookback_t]
    return (min(closes) >= level) if closes else True


# ── Anti-trend "father" filter ────────────────────────────────────

def _scan_detect_father(window_t, R55_pip: float, direction: str) -> bool:
    """direction='down' kills uptrends (looks for bearish father bars).
    direction='up'   kills downtrends (looks for bullish father bars).
    Triggers when 1-8 most-recent bars accumulate 40-100% R55 against the trend."""
    if R55_pip <= 0 or not window_t:
        return False
    cur_close = _C(window_t[-1])
    for n in range(1, _SCAN_FATHER_MAX_BARS + 1):
        if n > len(window_t):
            break
        first_open = _O(window_t[-n])
        if direction == 'down':
            move_pip = (first_open - cur_close) * 100
        else:
            move_pip = (cur_close - first_open) * 100
        pct = (move_pip / R55_pip) * 100
        if _SCAN_FATHER_MIN_PCT <= pct <= _SCAN_FATHER_MAX_PCT:
            return True
    return False


def _scan_lot(risk_pip: float, portfolio: float) -> float:
    """Lot = portfolio × 10% / SL(pip) — matches notebook + Mountain helper."""
    if risk_pip <= 0:
        return 0.0
    return round((portfolio * 0.10) / risk_pip, 2)


def _scan_swing_pair_min_body_ok(window_t, swing, thresh_body_pip: float) -> bool:
    """Both bars of a swing pair must have body > 4% R55 (notebook SL_MIN_BODY_PCT)."""
    bar_nums = swing.get('bar_nums') or []
    if len(bar_nums) < 2:
        return False
    base = window_t[0][0]
    bodies = []
    for bn in bar_nums:
        idx = bn - base
        if 0 <= idx < len(window_t):
            t = window_t[idx]
            bodies.append(abs(_C(t) - _O(t)) * 100)
    return bool(bodies) and min(bodies) > thresh_body_pip


# ── Public detectors ──────────────────────────────────────────────

def _detect_uptrend_scanner(bars: "list[OHLC]", portfolio: float = 1000.0):
    """Scanner v3.4 BUY detector. Returns Signal or None.

    Pipeline:
      1. C1-C6 on the trailing 55-bar window (with 25-bar lookback for C5/C6)
      2. Anti-trend "father" filter on the latest 1-8 bars
      3. Pick a swing low whose body_lo sits in the 65-85% R55 entry zone
      4. Trigger only when the current bar's Low has reached the swing low
      5. TP = entry + 50% × (highest swing high body_hi - entry)  (R:R=1.0 symmetric SL)"""
    from utils.swing_v414 import scan_swings

    if len(bars) < _SCAN_WINDOW:
        return None

    window = bars[-_SCAN_WINDOW:]
    window_t = _bars_to_tuples(window)
    lookback_t = _scan_lookback_tuples(bars)

    H55 = max(_H(b) for b in window_t)
    L55 = min(_L(b) for b in window_t)
    R55 = H55 - L55
    R55_pip = R55 * 100

    if R55 < _SCAN_MIN_R55_USD:
        return None

    if not (_scan_c1_up(window_t, L55, R55)
            and _scan_c2_up(window_t, L55, R55)
            and _scan_c3_up(window_t, R55)
            and _scan_c4_up(window_t, R55)
            and _scan_c5_up(lookback_t, R55)
            and _scan_c6_up(window_t, lookback_t, L55, R55)):
        return None

    if _scan_detect_father(window_t, R55_pip, direction='down'):
        return None

    cur = window_t[-1]
    cur_low = _L(cur)

    zone_lo = L55 + R55 * _SCAN_ZONE_UP_LO
    zone_hi = L55 + R55 * _SCAN_ZONE_UP_HI

    highs, lows = scan_swings(window_t, R55_pip)
    if not lows or not highs:
        return None

    thresh_body_pip = _SCAN_SL_MIN_BODY_PCT * R55_pip
    triggered = []
    for sl in lows:
        body_lo = sl['body_lo']
        if not (zone_lo <= body_lo <= zone_hi):
            continue
        if not _scan_swing_pair_min_body_ok(window_t, sl, thresh_body_pip):
            continue
        if cur_low <= body_lo:
            triggered.append(sl)
    if not triggered:
        return None
    sl_pick = max(triggered, key=lambda s: s['body_lo'])

    sh_body_hi = max(h['body_hi'] for h in highs)
    if sh_body_hi <= sl_pick['body_lo']:
        return None

    entry   = sl_pick['body_lo']
    reward  = sh_body_hi - entry
    tp_dist = 0.50 * reward
    tp      = entry + tp_dist
    sl      = entry - tp_dist
    risk_pip = tp_dist * 100
    if risk_pip <= 0:
        return None

    return Signal(
        pattern='UPTREND_SCANNER',
        direction='BUY',
        quality='✓',
        entry=round(entry, 3),
        sl=round(sl, 3),
        sl_name='SL=50%(SH-Entry)',
        tp_order=round(tp, 3),
        tp_ref=round(tp, 3),
        tp_name='TP=50%(SH-Entry)',
        rr=1.0,
        risk_pip=round(risk_pip, 1),
        reward_pip=round(tp_dist * 100, 1),
        lot=_scan_lot(risk_pip, portfolio),
        R55=round(R55_pip, 1),
        details={
            'L55': round(L55, 3), 'H55': round(H55, 3),
            'sl_body_lo': round(sl_pick['body_lo'], 3),
            'sl_bar_nums': sl_pick.get('bar_nums', []),
            'sh_body_hi': round(sh_body_hi, 3),
            'zone_lo': round(zone_lo, 3),
            'zone_hi': round(zone_hi, 3),
        },
    )


def _detect_downtrend_scanner(bars: "list[OHLC]", portfolio: float = 1000.0):
    """Scanner v3.4 SELL detector. Mirror of the BUY path."""
    from utils.swing_v414 import scan_swings

    if len(bars) < _SCAN_WINDOW:
        return None

    window = bars[-_SCAN_WINDOW:]
    window_t = _bars_to_tuples(window)
    lookback_t = _scan_lookback_tuples(bars)

    H55 = max(_H(b) for b in window_t)
    L55 = min(_L(b) for b in window_t)
    R55 = H55 - L55
    R55_pip = R55 * 100

    if R55 < _SCAN_MIN_R55_USD:
        return None

    if not (_scan_c1_down(window_t, H55, R55)
            and _scan_c2_down(window_t, H55, R55)
            and _scan_c3_down(window_t, R55)
            and _scan_c4_down(window_t, R55)
            and _scan_c5_down(lookback_t, R55)
            and _scan_c6_down(window_t, lookback_t, H55, R55)):
        return None

    if _scan_detect_father(window_t, R55_pip, direction='up'):
        return None

    cur = window_t[-1]
    cur_high = _H(cur)

    zone_lo = L55 + R55 * _SCAN_ZONE_DOWN_LO
    zone_hi = L55 + R55 * _SCAN_ZONE_DOWN_HI

    highs, lows = scan_swings(window_t, R55_pip)
    if not highs or not lows:
        return None

    thresh_body_pip = _SCAN_SL_MIN_BODY_PCT * R55_pip
    triggered = []
    for sh in highs:
        body_hi = sh['body_hi']
        if not (zone_lo <= body_hi <= zone_hi):
            continue
        if not _scan_swing_pair_min_body_ok(window_t, sh, thresh_body_pip):
            continue
        if cur_high >= body_hi:
            triggered.append(sh)
    if not triggered:
        return None
    sh_pick = min(triggered, key=lambda s: s['body_hi'])

    sl_body_lo = min(s['body_lo'] for s in lows)
    if sl_body_lo >= sh_pick['body_hi']:
        return None

    entry   = sh_pick['body_hi']
    reward  = entry - sl_body_lo
    tp_dist = 0.50 * reward
    tp      = entry - tp_dist
    sl      = entry + tp_dist
    risk_pip = tp_dist * 100
    if risk_pip <= 0:
        return None

    return Signal(
        pattern='DOWNTREND_SCANNER',
        direction='SELL',
        quality='✓',
        entry=round(entry, 3),
        sl=round(sl, 3),
        sl_name='SL=50%(Entry-SL)',
        tp_order=round(tp, 3),
        tp_ref=round(tp, 3),
        tp_name='TP=50%(Entry-SL)',
        rr=1.0,
        risk_pip=round(risk_pip, 1),
        reward_pip=round(tp_dist * 100, 1),
        lot=_scan_lot(risk_pip, portfolio),
        R55=round(R55_pip, 1),
        details={
            'L55': round(L55, 3), 'H55': round(H55, 3),
            'sh_body_hi': round(sh_pick['body_hi'], 3),
            'sh_bar_nums': sh_pick.get('bar_nums', []),
            'sl_body_lo': round(sl_body_lo, 3),
            'zone_lo': round(zone_lo, 3),
            'zone_hi': round(zone_hi, 3),
        },
    )
