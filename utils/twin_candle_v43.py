"""
Twin Candle V4.3 — 2 Roles Implementation

นิยามแท่งคู่ แบ่งออกเป็น 2 บทบาท:

1. Swing Point Role (ระบุ HH/HL/LH/LL):
   - ห่าง ≤ 50 pip
   - body ≥ 1% Range55

2. Entry Setup Role (จุดเข้าเทรด):
   - ห่าง ≤ 20 pip
   - body ≥ 3% Range55
   - มี beauty_score (60/80/90/100)

Swing High/Low Detection:
- ใช้สูตร mid = (C1+O2)÷2
- Lookback: ซ้าย 3 แท่ง + ขวา 2 แท่ง

Reference: XAUUSD_System_PromptV43.md Section "นิยามแท่งคู่ — มี 2 บทบาท"
"""

from typing import Tuple, Optional


# ============================================================================
# ROLE 1: SWING POINT DETECTION (ระบุ Swing Point)
# ============================================================================

def is_swing_candle_pair(c1: dict, c2: dict, range55: float) -> bool:
    """
    บทบาทที่ 1 — ระบุ Swing Point (HH/HL/LH/LL)

    เงื่อนไข:
      1. Open หรือ Close ของ 2 แท่ง ห่างกัน ≤ 50 pip
      2. เนื้อเทียน (|Open-Close|) แต่ละแท่ง ≥ 1% ของ Range55

    Args:
        c1: แท่งแรก {open, high, low, close}
        c2: แท่งที่สอง {open, high, low, close}
        range55: Range55 (USD)

    Returns:
        True ถ้าเป็นแท่งคู่ที่ใช้ระบุ Swing Point ได้

    Example:
        >>> is_swing_candle_pair(c1, c2, 50.0)  # R55=50 USD = 5000 pip
        True  # ถ้าห่าง 30pip และ body แต่ละแท่ง ≥ 50 pip (1%)
    """
    # เงื่อนไข 1: gap ≤ 50 pip
    gap_pip = abs(c1["close"] - c2["open"]) * 100
    if gap_pip > 50:
        return False

    # เงื่อนไข 2: body แต่ละแท่ง ≥ 1% R55
    body1_pip = abs(c1["open"] - c1["close"]) * 100
    body2_pip = abs(c2["open"] - c2["close"]) * 100
    min_body_pip = range55 * 100 * 0.01  # 1% R55 ใน pip

    if body1_pip < min_body_pip or body2_pip < min_body_pip:
        return False

    return True


# ============================================================================
# ROLE 2: ENTRY SETUP DETECTION (จุดเข้าเทรด)
# ============================================================================

def is_entry_candle_pair(
    c1: dict, c2: dict, range55: float
) -> Tuple[bool, int]:
    """
    บทบาทที่ 2 — Entry Setup (จุดเข้าเทรด)

    เงื่อนไข:
      1. Open หรือ Close ของ 2 แท่ง ห่างกัน ≤ 20 pip
      2. เนื้อเทียน (|Open-Close|) แต่ละแท่ง ≥ 3% ของ Range55

    คะแนนความสวย (วัดจาก body แท่งที่เล็กกว่า):
      - body > 3%  R55 → สวย  60% ⚠️
      - body > 4%  R55 → สวย  80% 🔶
      - body > 5%  R55 → สวย  90% ✅
      - body > 7%  R55 → สวย 100% ✅✅

    Args:
        c1: แท่งแรก {open, high, low, close}
        c2: แท่งที่สอง {open, high, low, close}
        range55: Range55 (USD)

    Returns:
        (valid: bool, beauty_score: int)
        - (True, 60-100) ถ้าเป็น Entry Setup ที่ใช้ได้
        - (False, 0) ถ้าไม่ผ่านเกณฑ์

    Example:
        >>> is_entry_candle_pair(c1, c2, 50.0)
        (True, 90)  # ห่าง 15pip, body min = 5.5%R55 → beauty 90
    """
    # เงื่อนไข 1: gap ≤ 20 pip
    gap_pip = abs(c1["close"] - c2["open"]) * 100
    if gap_pip > 20:
        return False, 0

    # เงื่อนไข 2: body แต่ละแท่ง ≥ 3% R55
    body1_pip = abs(c1["open"] - c1["close"]) * 100
    body2_pip = abs(c2["open"] - c2["close"]) * 100
    min_body_pip = min(body1_pip, body2_pip)  # วัดจากแท่งที่เล็กกว่า
    r55_pip = range55 * 100

    # ต้องผ่าน 3% ก่อน
    if min_body_pip < r55_pip * 0.03:
        return False, 0

    # คำนวณ beauty score
    if min_body_pip >= r55_pip * 0.07:
        beauty = 100
    elif min_body_pip >= r55_pip * 0.05:
        beauty = 90
    elif min_body_pip >= r55_pip * 0.04:
        beauty = 80
    else:  # 3-4%
        beauty = 60

    return True, beauty


# ============================================================================
# SWING HIGH/LOW DETECTION — V4.3 (C1+O2)÷2 METHOD
# ============================================================================

def is_swing_high_v43(
    candles: list, idx: int, range55: float
) -> bool:
    """
    Swing High V4.3 — ใช้สูตร (C1+O2)÷2

    Swing High = แท่งคู่ที่ mid สูงกว่า OC ทุกแท่ง ซ้าย3 + ขวา2

    ขั้นตอน:
      1. ต้องผ่าน is_swing_candle_pair ก่อน
      2. คำนวณ mid = (C1 + O2) ÷ 2
      3. ตรวจ mid > max(Open, Close) ของทุกแท่งข้างเคียง
         - ซ้าย 3 แท่ง (idx-3 ถึง idx-1)
         - ขวา 2 แท่ง (idx+2 ถึง idx+3)

    Args:
        candles: List of candles (55 แท่ง)
        idx: Index ของแท่งแรกในคู่ (c1)
        range55: Range55 (USD)

    Returns:
        True ถ้าเป็น Swing High

    Example:
        >>> candles = [...]  # 55 แท่ง
        >>> is_swing_high_v43(candles, 25, 50.0)
        True  # แท่ง 25-26 เป็น Swing High
    """
    # ต้องมีพื้นที่เพียงพอ: ซ้าย 3 + ขวา 2
    if idx < 3 or idx + 3 >= len(candles):
        return False

    c1 = candles[idx]
    c2 = candles[idx + 1]

    # ต้องผ่าน is_swing_candle_pair ก่อน
    if not is_swing_candle_pair(c1, c2, range55):
        return False

    # คำนวณ mid = (C1 + O2) ÷ 2
    mid = (c1["close"] + c2["open"]) / 2

    # ตรวจซ้าย 3 แท่ง (idx-3 ถึง idx-1)
    for i in range(idx - 3, idx):
        c = candles[i]
        if mid <= max(c["open"], c["close"]):
            return False

    # ตรวจขวา 2 แท่ง (idx+2 ถึง idx+3)
    for i in range(idx + 2, idx + 4):
        c = candles[i]
        if mid <= max(c["open"], c["close"]):
            return False

    return True


def is_swing_low_v43(
    candles: list, idx: int, range55: float
) -> bool:
    """
    Swing Low V4.3 — ใช้สูตร (C1+O2)÷2

    Swing Low = แท่งคู่ที่ mid ต่ำกว่า OC ทุกแท่ง ซ้าย3 + ขวา2

    ขั้นตอน:
      1. ต้องผ่าน is_swing_candle_pair ก่อน
      2. คำนวณ mid = (C1 + O2) ÷ 2
      3. ตรวจ mid < min(Open, Close) ของทุกแท่งข้างเคียง
         - ซ้าย 3 แท่ง (idx-3 ถึง idx-1)
         - ขวา 2 แท่ง (idx+2 ถึง idx+3)

    Args:
        candles: List of candles (55 แท่ง)
        idx: Index ของแท่งแรกในคู่ (c1)
        range55: Range55 (USD)

    Returns:
        True ถ้าเป็น Swing Low

    Example:
        >>> candles = [...]  # 55 แท่ง
        >>> is_swing_low_v43(candles, 25, 50.0)
        True  # แท่ง 25-26 เป็น Swing Low
    """
    # ต้องมีพื้นที่เพียงพอ: ซ้าย 3 + ขวา 2
    if idx < 3 or idx + 3 >= len(candles):
        return False

    c1 = candles[idx]
    c2 = candles[idx + 1]

    # ต้องผ่าน is_swing_candle_pair ก่อน
    if not is_swing_candle_pair(c1, c2, range55):
        return False

    # คำนวณ mid = (C1 + O2) ÷ 2
    mid = (c1["close"] + c2["open"]) / 2

    # ตรวจซ้าย 3 แท่ง (idx-3 ถึง idx-1)
    for i in range(idx - 3, idx):
        c = candles[i]
        if mid >= min(c["open"], c["close"]):
            return False

    # ตรวจขวา 2 แท่ง (idx+2 ถึง idx+3)
    for i in range(idx + 2, idx + 4):
        c = candles[i]
        if mid >= min(c["open"], c["close"]):
            return False

    return True


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def find_technical_price_v43(c1: dict, c2: dict) -> float:
    """
    หา Technical Price จากแท่งคู่ Entry
    = เนื้อเทียนด้านล่าง (body_lo) ของแท่งคู่

    Args:
        c1: แท่งแรก
        c2: แท่งที่สอง

    Returns:
        technical_price (float) = min(body1_lo, body2_lo)
    """
    body1_lo = min(c1["open"], c1["close"])
    body2_lo = min(c2["open"], c2["close"])
    return min(body1_lo, body2_lo)


def calculate_mid_price(c1: dict, c2: dict) -> float:
    """
    คำนวณ mid price = (C1 + O2) ÷ 2

    ใช้สำหรับระบุ Swing Point

    Args:
        c1: แท่งแรก
        c2: แท่งที่สอง

    Returns:
        mid_price (float)
    """
    return (c1["close"] + c2["open"]) / 2
