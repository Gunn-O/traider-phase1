# ============================================================================
# bt/strategies/_util.py
# ----------------------------------------------------------------------------
# Helper กลางที่ "หลายกลยุทธ์ใช้ร่วม" — R55 (window ปรับได้), lot sizing, bar helpers
# ย้ายมาจาก mai_ruay_v2 (pure move · พฤติกรรมต้องตรงเป๊ะ) เพื่อให้ mountain_v1 reuse
#
# *** pure functions ล้วน — ไม่มี state / ไม่มี logic ตัดสินใจของกลยุทธ์ ***
# (เกณฑ์เข้า/แบ่งไม้/TP-SL อยู่ในแต่ละ strategy · ไฟล์นี้เป็นแค่เครื่องคิดเลขร่วม)
# ============================================================================
from __future__ import annotations

import math

from bt.contract import Bar
from bt.data import PIP

_MIN_LOT = 0.01    # lot ขั้นต่ำ (ปัดต่อไม้: <0.01 → 0.01 · ≥0.01 → ปัดลงทีละ 0.01)


def _r(x, n):
    return round(float(x), n)


# ---------- lot sizing ต่อแผน (risk = lot × ระยะ SL · convention เดิม) ----------
def _round_lot(x: float) -> float:
    """ปัดต่อไม้: <0.01 → ปัดขึ้น 0.01 (min) · ≥0.01 → ปัดลงทีละ 0.01 (floor)"""
    if x < _MIN_LOT:
        return _MIN_LOT
    return math.floor(x * 100 + 1e-9) / 100


def _compute_lots(dists_pips, budget, split_mode):
    """คิด lot ต่อไม้จาก budget (= พอร์ต×risk%) · dists_pips = [ระยะ SL ต่อไม้ (pip), >0]
      - equal_risk (B): risk ต่อไม้ = budget/N → lot_i = (budget/N) / dist_i
      - equal_lot  (A): L = budget / Σdist → lot_i = L (เท่ากันทุกไม้)
    ปัดต่อไม้แล้วเช็ค total_risk = Σ(lot_i×dist_i); ถ้า > budget → ตัดไม้ "ตัวล่างสุด" (ท้าย legs) ออก
    คิดใหม่ วนจน ≤ budget หรือเหลือ 1 ไม้ · คืน list[lot] (ยาว = จำนวนไม้ที่เหลือ)"""
    n = len(dists_pips)
    while n >= 1:
        sub = dists_pips[:n]
        if split_mode == 'equal_lot':
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
        n -= 1   # เกิน budget → ตัดไม้ท้ายสุดออก 1 แล้วคิดใหม่
    return []


# ---------- R55 (window ปรับได้ตาม general.r55_bars — calc_r55 ใน data.py fix 55) ----------
def _calc_r55(bars, end_idx: int, n: int) -> float:
    start = max(0, end_idx - n + 1)
    window = bars[start:end_idx + 1]
    if not window:
        return 0.0
    hi = max(b.high for b in window)
    lo = min(b.low for b in window)
    return (hi - lo) / PIP


# ---------- bar helpers ----------
def _body_pips(b: Bar) -> float: return abs(b.open - b.close) / PIP
def _is_bull(b: Bar) -> bool:    return b.close > b.open
def _is_bear(b: Bar) -> bool:    return b.close < b.open


# ---------- swing pairs (port จาก v4.45 scan_swings · reuse ข้ามกลยุทธ์) ----------
# ต่างจาก mountain_v1.scan_pairs (ที่ใช้ mid + เช็คสีคู่): ตัวนี้ตรวจเพื่อนบ้านไม่ข้าม mid
#   (ซ้าย3+ขวา2 · แท่งหนา→ซ้าย1+ขวา1) + Doji extension + คืน body_lo/body_hi (จุดเทคนิคจริง)
#   ใช้โดย mountain_v3 (สเปก: docs/MOUNTAIN_V3_CLEAN_SPEC.md §STEP1) — pure function ไม่มี state
def _swing_ok(window, li, rj, mid, kind, thick, right2_exc) -> bool:
    """เพื่อนบ้านของแท่งคู่ต้องไม่ข้าม mid (high: O,C < mid ทุกตัว · low: O,C > mid)
      thick=True → ตรวจ ซ้าย1+ขวา1 (แท่งหนา) · ปกติ ซ้าย3+ขวา2
      เพื่อนซ้ายหลุดขอบข้อมูล (k<0) → ข้าม · เพื่อนขวาหลุดขอบ (k≥n) → คืน right2_exc"""
    left  = [li - 1] if thick else [li - 3, li - 2, li - 1]
    right = [rj + 1] if thick else [rj + 1, rj + 2]
    n = len(window)
    for k in left:
        if k < 0:
            continue
        b = window[k]
        if (b.open >= mid or b.close >= mid) if kind == 'high' else (b.open <= mid or b.close <= mid):
            return False
    for k in right:
        if k >= n:
            return right2_exc
        b = window[k]
        if (b.open >= mid or b.close >= mid) if kind == 'high' else (b.open <= mid or b.close <= mid):
            return False
    return True


def scan_swings(window, r55, join_max_pip, min_body_pct_r55, thick_exc_pct_r55, start: int = 0):
    """หาแท่งคู่ Swing High (Λ) / Low (V) ทั้งหมดใน window (port จาก v4.45)
      - join: |close_i − open_{i+1}| ≤ join_max_pip (pip)
      - body แต่ละแท่ง ≥ min_body_pct_r55%×R55 (pip) · แท่งหนา = body > thick_exc_pct_r55%×R55
      - mid = (close_i + open_{i+1})/2 · เพื่อนบ้านไม่ข้าม mid (_swing_ok)
      - Doji extension: แท่งใดในคู่ body<min → ขยายไปแท่งถัดไป (ซ้าย/ขวา) · ทั้งคู่ doji → ข้าม
      - right2 exception ปิด (right2_exc=False) — v3 detect ทุกแท่ง ไม่มี zone แบบ track
    คืน (highs, lows) · แต่ละตัว = {body_hi|body_lo, mid, bar=(i0+i1)/2, i0, i1, thick}
      bar/i0/i1 = index สัมบูรณ์ใน window (viewer S.X รับ bar float ได้)"""
    min_body = min_body_pct_r55 / 100 * r55
    thick_th = thick_exc_pct_r55 / 100 * r55
    n = len(window)
    highs, lows = [], []
    seen_h, seen_l = set(), set()

    def _try(li, rj, kind):
        seen = seen_h if kind == 'high' else seen_l
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
        rec = {'mid': mid, 'bar': (li + rj) / 2, 'i0': li, 'i1': rj, 'thick': thick}
        if kind == 'high':
            rec['body_hi'] = max(b1.open, b1.close, b2.open, b2.close)
            highs.append(rec)
        else:
            rec['body_lo'] = min(b1.open, b1.close, b2.open, b2.close)
            lows.append(rec)

    for i in range(max(0, start), n - 1):
        j = i + 1
        b1, b2 = window[i], window[j]
        if abs(b1.close - b2.open) / PIP > join_max_pip:   # คู่ติดกันห่างเกิน → ข้าม (parity v4.45)
            continue
        d1 = _body_pips(b1) < min_body
        d2 = _body_pips(b2) < min_body
        if not d1 and not d2:
            _try(i, j, 'high'); _try(i, j, 'low')
        elif not d1 and d2 and j + 1 < n:      # b2 doji → ขยายขวา
            _try(i, j + 1, 'high'); _try(i, j + 1, 'low')
        elif d1 and not d2 and i - 1 >= 0:      # b1 doji → ขยายซ้าย
            _try(i - 1, j, 'high'); _try(i - 1, j, 'low')
    return highs, lows
