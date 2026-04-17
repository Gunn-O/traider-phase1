"""
Pattern Detection Utility Functions

Helper functions สำหรับ G1 Pattern Detector
Reference: pattern_detection_spec.md v1.0
"""

import math
from typing import List, Dict, Tuple

from config import (
    CANDLES_LOOKBACK,
    SCREEN_X,
    SCREEN_Y,
    TARGET_SLOPE_DEG,
    MIN_TWIN_CANDLE_BODY,
    MAX_TWIN_CANDLE_GAP
)


# ============================================================================
# SLOPE CALCULATION
# ============================================================================

def calc_slope_angle(price_start: float, price_end: float,
                     candle_start: int, candle_end: int,
                     range_usd: float) -> float:
    """
    คำนวณมุมความชันของเส้นแนวโน้มบนหน้าจอ

    Args:
        price_start: ราคาเริ่มต้น
        price_end: ราคาสิ้นสุด
        candle_start: Index แท่งเริ่มต้น
        candle_end: Index แท่งสิ้นสุด
        range_usd: Range ของ 55 แท่ง (USD)

    Returns:
        องศา (0-90)

    Example:
        >>> calc_slope_angle(3200, 3250, 0, 40, 80)
        47.3
    """
    delta_price = abs(price_end - price_start)
    delta_candles = abs(candle_end - candle_start)

    if delta_candles == 0 or range_usd == 0:
        return 0.0

    # Normalize ให้อยู่ใน screen coordinate
    norm_y = delta_price / range_usd            # 0-1
    norm_x = delta_candles / CANDLES_LOOKBACK   # 0-1
    slope_screen = (norm_y / norm_x) * (SCREEN_X / SCREEN_Y)
    angle = math.degrees(math.atan(slope_screen))

    return round(angle, 1)


def is_good_slope(angle: float) -> bool:
    """
    ความชัน 45-50 องศา = Uptrend/Downtrend ที่ดี

    Args:
        angle: มุม (องศา)

    Returns:
        True ถ้าความชันดี (43-52°)
    """
    return 43.0 <= angle <= 52.0  # ±3° tolerance


def slope_quality(angle: float) -> float:
    """
    ให้คะแนน 0-1 ตามความใกล้เคียง 47.5°
    1.0 = ตรง 47.5° | 0.0 = ห่าง > 20°

    Args:
        angle: มุม (องศา)

    Returns:
        คะแนน 0.0-1.0
    """
    diff = abs(angle - TARGET_SLOPE_DEG)
    if diff > 20:
        return 0.0
    return round(1.0 - (diff / 20), 2)


# ============================================================================
# SWING POINTS DETECTION
# ============================================================================

def find_swing_points(candles: List[dict], window: int = 3) -> Dict:
    """
    หา swing highs และ swing lows จาก 55 แท่ง
    window: จำนวนแท่งรอบข้างที่ต้องสูง/ต่ำกว่า

    Args:
        candles: list of candle dicts
        window: window size (default: 3)

    Returns:
        {
            'highs': [(index, price), ...],
            'lows': [(index, price), ...]
        }
    """
    highs, lows = [], []

    for i in range(window, len(candles) - window):
        # Swing high: สูงกว่าทุกแท่งในระยะ window
        if all(candles[i]['high'] >= candles[j]['high']
               for j in range(i-window, i+window+1) if j != i):
            highs.append((i, candles[i]['high']))

        # Swing low: ต่ำกว่าทุกแท่งในระยะ window
        if all(candles[i]['low'] <= candles[j]['low']
               for j in range(i-window, i+window+1) if j != i):
            lows.append((i, candles[i]['low']))

    return {'highs': highs, 'lows': lows}


def check_hh_hl(swing_points: Dict, min_count: int = 3) -> Dict:
    """
    ตรวจ Higher High + Higher Low (Uptrend)

    Args:
        swing_points: output จาก find_swing_points()
        min_count: จำนวน HH/HL ขั้นต่ำ

    Returns:
        {
            'is_uptrend': bool,
            'hh_count': int,     # จำนวน HH ที่เจอ
            'hl_count': int,     # จำนวน HL ที่เจอ
            'consecutive': bool  # HH/HL ต่อเนื่องโดยไม่มีสวนทิศ
        }
    """
    highs = [p[1] for p in swing_points['highs']]
    lows = [p[1] for p in swing_points['lows']]

    if len(highs) < 2 or len(lows) < 2:
        return {'is_uptrend': False, 'hh_count': 0, 'hl_count': 0, 'consecutive': False}

    hh_count = sum(1 for i in range(1, len(highs)) if highs[i] > highs[i-1])
    hl_count = sum(1 for i in range(1, len(lows)) if lows[i] > lows[i-1])

    # ตรวจว่าไม่มี Lower Low สวนทิศ
    has_ll = any(lows[i] < lows[i-1] for i in range(1, len(lows)))

    return {
        'is_uptrend': hh_count >= min_count and hl_count >= min_count and not has_ll,
        'hh_count': hh_count,
        'hl_count': hl_count,
        'consecutive': not has_ll
    }


def check_lh_ll(swing_points: Dict, min_count: int = 3) -> Dict:
    """
    ตรวจ Lower High + Lower Low (Downtrend) — กลับทาง check_hh_hl

    Args:
        swing_points: output จาก find_swing_points()
        min_count: จำนวน LH/LL ขั้นต่ำ

    Returns:
        {
            'is_downtrend': bool,
            'lh_count': int,
            'll_count': int,
            'consecutive': bool
        }
    """
    highs = [p[1] for p in swing_points['highs']]
    lows = [p[1] for p in swing_points['lows']]

    if len(highs) < 2 or len(lows) < 2:
        return {'is_downtrend': False, 'lh_count': 0, 'll_count': 0, 'consecutive': False}

    lh_count = sum(1 for i in range(1, len(highs)) if highs[i] < highs[i-1])
    ll_count = sum(1 for i in range(1, len(lows)) if lows[i] < lows[i-1])

    # ตรวจว่าไม่มี Higher High สวนทิศ
    has_hh = any(highs[i] > highs[i-1] for i in range(1, len(highs)))

    return {
        'is_downtrend': lh_count >= min_count and ll_count >= min_count and not has_hh,
        'lh_count': lh_count,
        'll_count': ll_count,
        'consecutive': not has_hh
    }


# ============================================================================
# CANDLE ANALYSIS
# ============================================================================

def calc_candle_body(candle: dict) -> float:
    """
    คำนวณขนาดเนื้อเทียน (body)

    Args:
        candle: {open, high, low, close}

    Returns:
        body size (USD)
    """
    return abs(candle['close'] - candle['open'])


def calc_candle_range(candle: dict) -> float:
    """
    คำนวณ range ของแท่ง (high - low)

    Args:
        candle: {open, high, low, close}

    Returns:
        range (USD)
    """
    return candle['high'] - candle['low']


def is_bullish(candle: dict) -> bool:
    """ตรวจว่าแท่งเป็นขาขึ้น (close > open)"""
    return candle['close'] >= candle['open']


def is_bearish(candle: dict) -> bool:
    """ตรวจว่าแท่งเป็นขาลง (close < open)"""
    return candle['close'] < candle['open']


def calc_body_ratio(candle: dict) -> float:
    """
    คำนวณสัดส่วน body / range

    Args:
        candle: {open, high, low, close}

    Returns:
        body_ratio (0.0-1.0)
    """
    body = calc_candle_body(candle)
    candle_range = calc_candle_range(candle)
    if candle_range == 0:
        return 0.0
    return round(body / candle_range, 2)


# ============================================================================
# TWIN CANDLE DETECTION
# ============================================================================

def is_twin_candle(c1: dict, c2: dict, range_usd: float) -> bool:
    """
    ตรวจว่า 2 แท่งเป็นแท่งคู่หรือไม่

    เงื่อนไข:
    1. ขนาดเนื้อเทียน ≥ 5% ของ Range
    2. Open/Close ห่างกัน ≤ 10 pip

    Args:
        c1: แท่งแรก
        c2: แท่งที่สอง
        range_usd: Range ของ 55 แท่ง (USD)

    Returns:
        True ถ้าเป็นแท่งคู่
    """
    # เงื่อนไข 1: ขนาดเนื้อเทียน
    body1 = calc_candle_body(c1)
    body2 = calc_candle_body(c2)

    if body1 < range_usd * MIN_TWIN_CANDLE_BODY or body2 < range_usd * MIN_TWIN_CANDLE_BODY:
        return False

    # เงื่อนไข 2: Gap ระหว่าง c1 close ถึง c2 open ≤ threshold pip
    gap = abs(c1['close'] - c2['open']) * 100  # pip

    if gap > MAX_TWIN_CANDLE_GAP:
        return False

    return True


def find_technical_price(c1: dict, c2: dict) -> float:
    """
    หา Technical Price จากแท่งคู่
    = เนื้อเทียนด้านล่าง (body low) ของแท่งคู่

    ตาม Strategy v2.1:
    - Twin Candle: "จดจำ เนื้อเทียนด้านล่าง → จุดเทคนิค"
    - รอให้ราคาวกกลับมาแตะจุดเทคนิค

    Args:
        c1: แท่งแรก
        c2: แท่งที่สอง

    Returns:
        technical_price (float) = เนื้อเทียนด้านล่างของแท่งคู่
    """
    # Body low = min(open, close) ของแต่ละแท่ง
    body1_low = min(c1['open'], c1['close'])
    body2_low = min(c2['open'], c2['close'])

    # Technical price = เนื้อด้านล่างของทั้ง 2 แท่ง
    return round(min(body1_low, body2_low), 2)


# ============================================================================
# RANGE CALCULATION
# ============================================================================

def calc_range(candles: List[dict]) -> Dict:
    """
    คำนวณ Range ของ 55 แท่ง (หรือจำนวนแท่งที่ให้มา)

    Args:
        candles: list of 55 candles (newest last)

    Returns:
        {
            'high': float,      # High สูงสุด
            'low': float,       # Low ต่ำสุด
            'range': float,     # high - low (USD)
            'range_pip': int    # range × 100 (pip)
        }
    """
    if not candles:
        return {'high': 0, 'low': 0, 'range': 0, 'range_pip': 0}

    high = max(c['high'] for c in candles)
    low = min(c['low'] for c in candles)
    range_usd = high - low

    return {
        'high': high,
        'low': low,
        'range': range_usd,
        'range_pip': int(range_usd * 100)
    }


# ============================================================================
# SESSION DETECTION
# ============================================================================

def detect_session(timestamp) -> str:
    """
    ระบุ trading session จาก timestamp
    UTC timezone

    Args:
        timestamp: datetime object (UTC)

    Returns:
        'Asia' | 'London' | 'NY' | 'Unknown'
    """
    from datetime import time

    hour = timestamp.hour  # UTC hour

    # Asia: 00:00-08:00 UTC
    if 0 <= hour < 8:
        return 'Asia'
    # London: 08:00-16:00 UTC
    elif 8 <= hour < 16:
        return 'London'
    # NY: 13:00-22:00 UTC (overlap with London 13-16)
    elif 13 <= hour < 22:
        return 'NY'
    else:
        return 'Unknown'
