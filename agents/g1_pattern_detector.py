"""
G1 — Multi-TF Visual Pattern Detector

หน้าที่:
- Scan 6 TF (H4, H1, M30, M15, M5, M1) และตรวจจับ chart patterns
- ตรวจจับ 6 Chart Types: uptrend, downtrend, sideway_down, sideway_up, mountain, unclear
- ตรวจจับ 4 Techniques: twin_candle, breakout_follow, mai_ruay, support_bounce
- Select best setup โดย MTF tiebreak rules
- Output: world_state → ส่งต่อ G2

Reference: pattern_detection_spec.md v1.0
"""

import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime

from config import CANDLES_LOOKBACK, TIMEFRAMES, TF_SIZE
from utils.pattern_utils import (
    calc_range,
    calc_slope_angle,
    slope_quality,
    is_good_slope,
    find_swing_points,
    merge_close_swings,
    check_hh_hl,
    check_lh_ll,
    calc_candle_body,
    calc_candle_range,
    is_twin_candle,
    find_technical_price,
    detect_session
)
from utils.indicators import calculate_rsi

# Setup logging
logger = logging.getLogger(__name__)


# ============================================================================
# SETUP PRIORITY (ใช้ใน MTF tiebreak)
# ============================================================================

SETUP_PRIORITY = {
    'uptrend': 1,
    'downtrend': 1,
    'sideway_down': 2,
    'sideway_up': 2,
    'mountain': 3,
    'unclear': 4
}

TECHNIQUE_PRIORITY = {
    'twin_candle': 1,
    'breakout_follow': 2,
    'mai_ruay': 3,
    'support_bounce': 4
}


# ============================================================================
# CHART TYPE DETECTION
# ============================================================================

def detect_uptrend(candles: List[dict], range_data: dict, timeframe: str = 'M5') -> dict:
    """
    ตรวจ Uptrend: Higher High + Higher Low ต่อเนื่อง

    Returns:
        {
            'detected': bool,
            'quality': float (0.0-1.0),
            'slope_angle': float,
            'hh_hl': dict
        }
    """
    swings = find_swing_points(candles, timeframe)
    swings = merge_close_swings(swings)  # Merge pivots within 10 pip
    hh_hl = check_hh_hl(swings, min_count=2)  # Relax จาก 3 → 2

    # Relax: ถ้ามี HH/HL >= 2 ก็ให้ผ่านไปคำนวณ quality (แม้ไม่ consecutive)
    if hh_hl['hh_count'] < 2 or hh_hl['hl_count'] < 2:
        return {'detected': False, 'quality': 0.0}

    # คำนวณความชันจาก Low แรก → High ล่าสุด
    first_low_idx = swings['lows'][0][0] if swings['lows'] else 0
    last_high_idx = swings['highs'][-1][0] if swings['highs'] else len(candles)-1
    first_low_price = swings['lows'][0][1] if swings['lows'] else candles[0]['low']
    last_high_price = swings['highs'][-1][1] if swings['highs'] else candles[-1]['high']

    angle = calc_slope_angle(first_low_price, last_high_price,
                             first_low_idx, last_high_idx,
                             range_data['range'])

    slope_q = slope_quality(angle)
    continuity_q = 1.0 if hh_hl['consecutive'] else 0.5
    count_q = min(hh_hl['hh_count'] / 5, 1.0)

    quality = round((slope_q * 0.5) + (continuity_q * 0.3) + (count_q * 0.2), 2)

    return {
        'detected': quality >= 0.5,
        'quality': quality,
        'slope_angle': angle,
        'hh_hl': hh_hl
    }


def detect_downtrend(candles: List[dict], range_data: dict, timeframe: str = 'M5') -> dict:
    """
    ตรวจ Downtrend: Lower High + Lower Low ต่อเนื่อง (กลับทาง uptrend)
    """
    swings = find_swing_points(candles, timeframe)
    swings = merge_close_swings(swings)  # Merge pivots within 10 pip
    lh_ll = check_lh_ll(swings, min_count=2)  # Relax จาก 3 → 2

    # Relax: ถ้ามี LH/LL >= 2 ก็ให้ผ่านไปคำนวณ quality (แม้ไม่ consecutive)
    if lh_ll['lh_count'] < 2 or lh_ll['ll_count'] < 2:
        return {'detected': False, 'quality': 0.0}

    first_high_idx = swings['highs'][0][0] if swings['highs'] else 0
    last_low_idx = swings['lows'][-1][0] if swings['lows'] else len(candles)-1
    first_high_price = swings['highs'][0][1] if swings['highs'] else candles[0]['high']
    last_low_price = swings['lows'][-1][1] if swings['lows'] else candles[-1]['low']

    angle = calc_slope_angle(first_high_price, last_low_price,
                             first_high_idx, last_low_idx,
                             range_data['range'])

    slope_q = slope_quality(angle)
    continuity_q = 1.0 if lh_ll['consecutive'] else 0.5
    count_q = min(lh_ll['lh_count'] / 5, 1.0)

    quality = round((slope_q * 0.5) + (continuity_q * 0.3) + (count_q * 0.2), 2)

    return {
        'detected': quality >= 0.5,
        'quality': quality,
        'slope_angle': angle,
        'lh_ll': lh_ll
    }


def detect_sideway(candles: List[dict], range_data: dict) -> dict:
    """
    ตรวจ Sideway Press Down / Up
    เงื่อนไข: ขาพุ่ง 3-10 แท่ง 80-100% Range + กรอบ ≤ 50% Range

    Returns:
        {
            'detected': bool,
            'type': 'sideway_down' | 'sideway_up' | None,
            'quality': float,
            'impulse_candles': int,
            'impulse_pct': float,
            'box_high': float,
            'box_low': float,
            'box_pct': float,
            'current_position': 'near_top' | 'near_bottom' | 'middle'
        }
    """
    R = range_data['range']

    # หาขาพุ่ง (impulse leg)
    impulse = find_impulse_leg(candles, R)
    if not impulse['found']:
        return {'detected': False, 'type': None, 'quality': 0.0}

    # ตรวจกรอบ Sideway หลังขาพุ่ง
    remaining = candles[impulse['end_idx']:]
    if len(remaining) < 5:
        return {'detected': False, 'type': None, 'quality': 0.0}

    box_high = max(c['high'] for c in remaining)
    box_low = min(c['low'] for c in remaining)
    box_size = box_high - box_low
    box_pct = box_size / R

    if box_pct > 0.50:  # กรอบใหญ่เกิน 50% = ไม่ชัด
        return {'detected': False, 'type': None, 'quality': 0.0}

    # ตรวจตำแหน่งราคาปัจจุบัน
    current_price = candles[-1]['close']
    if current_price >= box_high - (box_size * 0.15):
        position = 'near_top'
    elif current_price <= box_low + (box_size * 0.15):
        position = 'near_bottom'
    else:
        position = 'middle'

    sideway_type = 'sideway_down' if impulse['direction'] == 'down' else 'sideway_up'

    # Quality
    impulse_q = min(impulse['pct'] / 0.8, 1.0)
    box_q = 1.0 - (box_pct / 0.5)
    quality = round((impulse_q * 0.6) + (box_q * 0.4), 2)

    return {
        'detected': quality >= 0.5,
        'type': sideway_type,
        'quality': quality,
        'impulse_candles': impulse['count'],
        'impulse_pct': impulse['pct'],
        'impulse_end_idx': impulse['end_idx'],
        'box_high': box_high,
        'box_low': box_low,
        'box_pct': box_pct,
        'current_position': position
    }


def find_impulse_leg(candles: List[dict], range_usd: float) -> dict:
    """
    หากลุ่มแท่ง 3-10 แท่งที่เคลื่อน 60-100% ของ Range ทิศทางเดียว
    """
    for start in range(len(candles) - 10):
        for count in range(3, 11):
            end = start + count
            if end >= len(candles):
                break
            group = candles[start:end]

            # ทุกแท่งต้องเป็นสีเดียวกัน
            is_bearish = all(c['close'] < c['open'] for c in group)
            is_bullish = all(c['close'] > c['open'] for c in group)

            if not (is_bearish or is_bullish):
                continue

            price_move = abs(group[-1]['close'] - group[0]['open'])
            pct = price_move / range_usd

            if pct >= 0.60:
                return {
                    'found': True,
                    'start_idx': start,
                    'end_idx': end,
                    'count': count,
                    'pct': round(pct, 2),
                    'direction': 'down' if is_bearish else 'up'
                }

    return {'found': False}


def detect_mountain(candles: List[dict], range_data: dict, timeframe: str = 'M5') -> dict:
    """
    ตรวจภูเขา: ขึ้น-ยอด-ลง ใน 55 แท่ง
    เงื่อนไข: ความสูง > 50% Range, ลงกลับฐานภายใน 55 แท่ง
    """
    R = range_data['range']
    swings = find_swing_points(candles, timeframe)
    swings = merge_close_swings(swings)  # Merge pivots within 10 pip

    if not swings['highs'] or len(swings['lows']) < 2:
        return {'detected': False, 'quality': 0.0}

    # หายอดสูงสุด
    peak_idx, peak_price = max(swings['highs'], key=lambda x: x[1])

    # ฐานซ้าย = swing low ก่อนยอด
    left_lows = [(i, p) for i, p in swings['lows'] if i < peak_idx]
    if not left_lows:
        return {'detected': False, 'quality': 0.0}
    left_base_idx, left_base_price = min(left_lows, key=lambda x: x[1])

    # ความสูงภูเขา
    height = peak_price - left_base_price
    height_pct = height / R
    if height_pct <= 0.50:
        return {'detected': False, 'quality': 0.0}

    # ตรวจว่าราคาปัจจุบันกลับมาใกล้ฐานซ้ายแล้วหรือยัง
    current_price = candles[-1]['close']
    tolerance = min(R * 0.05, 3.0)  # 5% Range หรือ 300 pip (3 USD)
    near_base = abs(current_price - left_base_price) <= tolerance

    # แท่งที่ใช้วกกลับ
    return_candles = len(candles) - 1 - peak_idx

    # หาแท่งคู่ที่ฐานซ้าย
    twin = find_twin_candle_nearby(candles, left_base_idx, left_base_price, R)

    # Quality scoring
    height_q = min(height_pct / 1.0, 1.0)
    speed_q = 1.0 if return_candles <= 40 else max(0, 1.0 - (return_candles-40)/15)
    shape_q = calc_mountain_shape(candles, left_base_idx, peak_idx)

    quality = round((height_q * 0.4) + (speed_q * 0.3) + (shape_q * 0.3), 2)

    return {
        'detected': quality >= 0.5 and near_base,
        'quality': quality,
        'peak_idx': peak_idx,
        'peak_price': peak_price,
        'left_base_price': left_base_price,
        'right_base_price': current_price,
        'height_pct': round(height_pct, 2),
        'height_usd': round(height, 2),
        'return_candles': return_candles,
        'twin_candle_base': twin,
        'tolerance_ok': near_base,
        'tolerance_usd': tolerance
    }


def calc_mountain_shape(candles: List[dict], base_idx: int, peak_idx: int) -> float:
    """
    คะแนนรูปทรงสามเหลี่ยม: 1.0 = สมมาตรสมบูรณ์
    """
    left_len = peak_idx - base_idx
    right_len = len(candles) - 1 - peak_idx
    if left_len == 0 or right_len == 0:
        return 0.0
    symmetry = 1.0 - abs(left_len - right_len) / max(left_len, right_len)
    return round(symmetry, 2)


def detect_father_candle(candles: List[dict], range_data: dict) -> dict:
    """
    หาแท่งพ่อ: 1-5 แท่งที่เคลื่อน 60-100% Range ทิศทางเดียว
    สำหรับ Technique "ไม้รวย" (mai_ruay)
    """
    R = range_data['range']

    # ตรวจย้อนหลังจากแท่งล่าสุด
    for end_idx in range(len(candles)-2, max(0, len(candles)-15), -1):
        for count in range(1, 6):
            start_idx = end_idx - count + 1
            if start_idx < 0:
                break

            group = candles[start_idx:end_idx+1]
            is_bearish = all(c['close'] < c['open'] for c in group)
            is_bullish = all(c['close'] > c['open'] for c in group)

            if not (is_bearish or is_bullish):
                continue

            price_move = abs(group[-1]['close'] - group[0]['open'])
            pct = price_move / R

            if pct < 0.60:
                continue

            direction = 'down' if is_bearish else 'up'

            # ตรวจแท่งแม่
            mother_idx = end_idx + 1
            if mother_idx >= len(candles):
                mother = {'found': False, 'valid': False}
            else:
                mother = check_mother_candle(
                    candles[mother_idx], group[-1], direction, R
                )

            # Quality
            pct_q = min((pct - 0.6) / 0.4, 1.0)
            count_q = 1.0 - ((count-1) / 4 * 0.3)
            quality = round((pct_q * 0.7) + (count_q * 0.3), 2)

            return {
                'found': True,
                'quality': quality,
                'start_idx': start_idx,
                'end_idx': end_idx,
                'direction': direction,
                'pct_range': round(pct, 2),
                'candle_count': count,
                'mother_candle': mother,
                'is_valid': mother.get('valid', False)
            }

    return {'found': False, 'quality': 0.0}


def check_mother_candle(mother: dict, last_father: dict,
                        father_direction: str, range_usd: float) -> dict:
    """
    ตรวจแท่งแม่:
    - ปิดสวนทิศกับแท่งพ่อ
    - ขนาดเนื้อ 5-40% ของแท่งพ่อ
    """
    father_body = abs(last_father['close'] - last_father['open'])
    mother_body = abs(mother['close'] - mother['open'])

    if father_body == 0:
        return {'found': True, 'valid': False}

    # ปิดสวนทิศ
    if father_direction == 'down':
        reversed_close = mother['close'] > mother['open']
    else:
        reversed_close = mother['close'] < mother['open']

    body_ratio = mother_body / father_body

    # ประเมินความสวย
    if 0.05 <= body_ratio <= 0.20:
        beauty = 'excellent'
    elif 0.20 < body_ratio <= 0.30:
        beauty = 'acceptable'
    elif 0.30 < body_ratio <= 0.40:
        beauty = 'poor'
    else:
        beauty = 'invalid'

    valid = reversed_close and beauty != 'invalid'

    technical_price = last_father['close']

    return {
        'found': True,
        'valid': valid,
        'reversed_close': reversed_close,
        'body_ratio': round(body_ratio, 3),
        'beauty': beauty,
        'technical_price': technical_price
    }


# ============================================================================
# TWIN CANDLE & BREAKOUT BOX DETECTION
# ============================================================================

def detect_twin_candle(candles: List[dict], range_data: dict, swings: dict = None) -> dict:
    """
    หาแท่งคู่ทั่วไป (สำหรับทุก chart type)
    ตรวจ 15 แท่งล่าสุด หา twin candle ที่ตรงเงื่อนไข

    Validation (ถ้ามี swings):
    - แท่งคู่ต้องอยู่ใกล้ swing point (swing low สำหรับ BUY setup, swing high สำหรับ SELL setup)
    - "ใกล้" = ห่างกันไม่เกิน 0.20 USD (20 pip)

    Args:
        candles: list of 55 candles
        range_data: {'range': float, ...}
        swings: {'highs': [(idx, price), ...], 'lows': [...]} (optional)

    Returns:
        {'found': bool, 'candle1_idx': int, 'candle2_idx': int, 'technical_price': float, 'body_pct': float}
    """
    range_usd = range_data['range']

    # ตรวจ 15 แท่งล่าสุด (เพียงพอสำหรับ setup)
    search_candles = candles[-15:] if len(candles) > 15 else candles
    search_offset = len(candles) - len(search_candles)

    for i in range(len(search_candles) - 1):
        c1 = search_candles[i]
        c2 = search_candles[i + 1]

        # ใช้ is_twin_candle() ที่มีเงื่อนไขครบถ้วน
        if is_twin_candle(c1, c2, range_usd):
            tech_price = find_technical_price(c1, c2)
            body1 = calc_candle_body(c1)
            body2 = calc_candle_body(c2)

            # Validate กับ swing points (ถ้ามี)
            if swings is not None:
                # ตรวจว่า tech_price ใกล้ swing low หรือ swing high
                near_swing_low = any(abs(tech_price - swing_price) <= 0.20
                                     for _, swing_price in swings.get('lows', []))
                near_swing_high = any(abs(tech_price - swing_price) <= 0.20
                                      for _, swing_price in swings.get('highs', []))

                # แท่งคู่ต้องอยู่ใกล้ swing point อย่างน้อย 1 จุด
                if not (near_swing_low or near_swing_high):
                    continue  # ไม่ผ่าน validation → ลองแท่งถัดไป

            return {
                'found': True,
                'candle1_idx': search_offset + i,
                'candle2_idx': search_offset + i + 1,
                'technical_price': tech_price,
                'body_pct': round(min(body1, body2) / range_usd, 3)
            }

    return {'found': False}


def find_twin_candle_nearby(candles: List[dict], search_start: int,
                            near_price: float, range_usd: float) -> dict:
    """
    หาแท่งคู่ใกล้ near_price (สำหรับ mountain base detection)
    """
    from config import MIN_TWIN_CANDLE_BODY, MAX_TWIN_CANDLE_GAP

    min_body = range_usd * MIN_TWIN_CANDLE_BODY
    max_gap = MAX_TWIN_CANDLE_GAP / 100  # convert pip to USD

    search_range = range(max(0, search_start-5),
                         min(len(candles)-1, search_start+10))

    for i in search_range:
        for j in [i+1, i-1]:
            if j < 0 or j >= len(candles):
                continue
            c1, c2 = candles[i], candles[j]

            # ใช้ is_twin_candle() แทน (แก้บัค gap check แล้ว)
            if is_twin_candle(c1, c2, range_usd):
                tech_price = find_technical_price(c1, c2)
                body1 = calc_candle_body(c1)
                body2 = calc_candle_body(c2)
                return {
                    'found': True,
                    'candle1_idx': i,
                    'candle2_idx': j,
                    'technical_price': tech_price,
                    'body_pct': round(min(body1, body2) / range_usd, 3)
                }

    return {'found': False}


def detect_breakout_box(candles: List[dict], range_data: dict,
                        chart_type: str, swings: dict = None) -> dict:
    """
    หากรอบเล็กๆ ระหว่างเทรน สำหรับ Technique ตามเจ้า
    เงื่อนไข: กรอบบน-ล่าง ≤ 35% ของ Range

    ถ้ามี swings → ใช้ swing highs/lows ใน 15 แท่งล่าสุดเป็นกรอบ (accurate กว่า)
    ถ้าไม่มี swings → fallback ใช้ max/min ปกติ

    Args:
        candles: list of 55 candles
        range_data: {'range': float, ...}
        chart_type: uptrend/downtrend/mountain
        swings: {'highs': [(idx, price), ...], 'lows': [...]} (optional)

    Returns:
        {'found': bool, 'box_high': float, 'box_low': float, 'box_pct': float, 'breakout_direction': str}
    """
    if chart_type not in ['uptrend', 'downtrend', 'mountain']:
        return {'found': False}

    R = range_data['range']
    max_box = R * 0.35

    # มองแท่ง 15 แท่งล่าสุด
    recent_start_idx = len(candles) - 15

    # ใช้ swing points ถ้ามี (accurate กว่า)
    if swings is not None and swings.get('highs') and swings.get('lows'):
        # Filter swing points ใน 15 แท่งล่าสุด
        recent_swing_highs = [price for idx, price in swings['highs'] if idx >= recent_start_idx]
        recent_swing_lows = [price for idx, price in swings['lows'] if idx >= recent_start_idx]

        # ต้องมี swing point อย่างน้อย 1 จุด
        if recent_swing_highs and recent_swing_lows:
            box_high = max(recent_swing_highs)
            box_low = min(recent_swing_lows)
        else:
            # Fallback: ใช้ max/min ปกติ
            recent = candles[-15:]
            box_high = max(c['high'] for c in recent)
            box_low = min(c['low'] for c in recent)
    else:
        # Fallback: ใช้ max/min ปกติ
        recent = candles[-15:]
        box_high = max(c['high'] for c in recent)
        box_low = min(c['low'] for c in recent)

    box_size = box_high - box_low

    if box_size > max_box:
        return {'found': False}

    # ตรวจ breakout direction
    last = candles[-1]
    if last['close'] > box_high - (box_size * 0.1):
        breakout = 'up'
    elif last['close'] < box_low + (box_size * 0.1):
        breakout = 'down'
    else:
        breakout = None

    return {
        'found': True,
        'box_high': box_high,
        'box_low': box_low,
        'box_pct': round(box_size / R, 2),
        'breakout_direction': breakout
    }


# Continue in next part...


# ============================================================================
# MTF SELECTION & WORLD STATE BUILDER
# ============================================================================

def select_best_setup(tf_results: dict) -> dict:
    """
    เลือก TF และ Setup ที่ดีที่สุดจาก 6 TF

    กฎตาม Strategy Section 4.2 + Setup Readiness:
    1. กรองTF ที่ technique = 'skip' ออก (ไม่มี setup)
       - ยอมรับ unclear+mai_ruay (Strategy Section 1.7)
    2. ถ้าเหลือ 0 TF → SKIP
    3. คำนวณ score = quality + setup_bonus (0.20 ถ้ามี setup พร้อมใช้)
    4. เลือก TF ที่ score สูงสุด
    5. ถ้า score เท่ากัน → เลือก TF ที่ใหญ่กว่า (TF_SIZE)

    Setup readiness = มี twin_candle, father_candle, breakout_box,
                      หรือ mountain พร้อมเข้า (tolerance_ok)

    Returns:
        {'tf': str, 'chart_type': str, 'quality': float, ...}
    """
    # กรอง TF: ต้องมี technique ที่ใช้ได้ (ไม่ใช่ 'skip')
    def is_valid_tf(result):
        technique = result.get('technique_candidate', 'skip')

        # ถ้า technique = 'skip' → ตก (ไม่มี setup)
        if technique == 'skip':
            return False

        # มี technique ที่ใช้ได้ → ผ่าน
        # รวมถึง unclear+mai_ruay (Strategy Section 1.7)
        return True

    # Log TF filtering
    for tf, r in tf_results.items():
        technique = r.get('technique_candidate', 'skip')
        chart_type = r.get('chart_type', 'unknown')
        quality = r.get('quality', 0)

        if is_valid_tf(r):
            logger.debug(f"  {tf}: {chart_type} (quality={quality:.2f}) → {technique} ✓")
        else:
            logger.debug(f"  {tf}: {chart_type} (quality={quality:.2f}) → {technique} ✗ (filtered)")

    valid = {tf: r for tf, r in tf_results.items() if is_valid_tf(r)}

    if not valid:
        logger.info("All TF have technique='skip' (no setups found) → SKIP")
        return {'tf': None, 'chart_type': 'unclear', 'quality': 0.0}

    # คำนวณ score สำหรับแต่ละ TF
    def calculate_score(result):
        """Calculate final score = quality + setup_bonus"""
        chart_quality = result.get('quality', 0)

        # Check setup readiness
        has_twin = result.get('twin_candle', {}).get('found', False)
        has_father = result.get('father_candle', {}).get('found', False) and \
                     result.get('father_candle', {}).get('is_valid', False)
        has_box = result.get('chart_detail', {}).get('breakout_box', {}).get('found', False)

        # Mountain: ต้องมี tolerance_ok ด้วย
        is_mountain_ready = (result.get('chart_type') == 'mountain' and
                            result.get('chart_detail', {}).get('tolerance_ok', False))

        has_setup = has_twin or has_father or has_box or is_mountain_ready

        # Setup bonus: +0.20 if setup พร้อมใช้
        setup_bonus = 0.20 if has_setup else 0.0

        final_score = chart_quality + setup_bonus
        return final_score

    # Sort: score DESC, TF_SIZE DESC (tiebreak)
    def sort_key(item):
        tf, r = item
        score = calculate_score(r)
        return (-score, -TF_SIZE.get(tf, 0))

    sorted_results = sorted(valid.items(), key=sort_key)
    best_tf, best_result = sorted_results[0]

    # Log scoring details
    best_score = calculate_score(best_result)
    has_any_setup = best_score > best_result.get('quality', 0)
    chart_type = best_result.get('chart_type', 'unknown')
    technique = best_result.get('technique_candidate', 'unknown')

    logger.info(f"Selected {best_tf} (chart={chart_type}, technique={technique}, "
                f"quality={best_result.get('quality', 0):.2f}, score={best_score:.2f}, "
                f"has_setup={has_any_setup})")

    return {
        'tf': best_tf,
        **best_result
    }


def build_world_state(candles: List[dict], timeframe: str, range_data: dict) -> dict:
    """
    รวม output ทั้งหมดเป็น world_state JSON
    ส่งให้ G2 และ G3a

    Returns:
        {
            'timeframe': str,
            'chart_type': str,
            'chart_quality': float,
            'chart_detail': dict,
            'technique_candidate': str,
            'range': dict,
            'father_candle': dict,
            'twin_candle': dict,
            'current_price': float,
            'session': str,
            'metadata': dict
        }
    """
    swings = find_swing_points(candles, timeframe)
    swings = merge_close_swings(swings)  # Merge pivots within 10 pip

    # Detect ทุก chart type
    uptrend = detect_uptrend(candles, range_data, timeframe)
    downtrend = detect_downtrend(candles, range_data, timeframe)
    sideway = detect_sideway(candles, range_data)
    mountain = detect_mountain(candles, range_data, timeframe)
    father = detect_father_candle(candles, range_data)

    # Detect twin candle (for all chart types) — validate with swing points
    twin = detect_twin_candle(candles, range_data, swings)

    # เลือก chart_type
    if uptrend['detected']:
        chart_type = 'uptrend'
        quality = uptrend['quality']
        chart_detail = uptrend
    elif downtrend['detected']:
        chart_type = 'downtrend'
        quality = downtrend['quality']
        chart_detail = downtrend
    elif sideway['detected']:
        chart_type = sideway['type']  # sideway_down or sideway_up
        quality = sideway['quality']
        chart_detail = sideway
    elif mountain['detected']:
        chart_type = 'mountain'
        quality = mountain['quality']
        chart_detail = mountain
    else:
        chart_type = 'unclear'
        quality = 0.0
        chart_detail = {}

    # Technique candidate
    technique = determine_technique(chart_type, chart_detail, father, twin, candles, range_data, swings)

    # Metadata (ไม่ใช้ตัดสิน)
    closes = [c['close'] for c in candles]
    if len(closes) >= 14:
        import pandas as pd
        df = pd.DataFrame(candles)
        rsi_series = calculate_rsi(df, period=14)
        rsi_val = float(rsi_series.iloc[-1]) if not rsi_series.empty else 50.0
    else:
        rsi_val = 50.0

    # Calculate slope metadata (for uptrend/downtrend only)
    slope_norm = 0.0
    trend_consistent = False
    if chart_type == 'uptrend':
        slope_angle = chart_detail.get('slope_angle', 0)
        slope_norm = slope_quality(slope_angle)  # 0-1 based on distance from 47.5°
        trend_consistent = chart_detail.get('hh_hl', {}).get('consecutive', False)
    elif chart_type == 'downtrend':
        slope_angle = chart_detail.get('slope_angle', 0)
        slope_norm = slope_quality(slope_angle)
        trend_consistent = chart_detail.get('lh_ll', {}).get('consecutive', False)

    return {
        'timeframe': timeframe,
        'chart_type': chart_type,
        'quality': quality,  # Changed from 'chart_quality'
        'chart_detail': chart_detail,
        'technique_candidate': technique,
        'range': {
            'high': range_data['high'],
            'low': range_data['low'],
            'usd': range_data['range'],
            'pip': range_data['range_pip']
        },
        'swing_points': swings,
        'father_candle': father,
        'twin_candle': twin,  # Use globally detected twin, not just mountain's twin_candle_base
        'current_price': candles[-1]['close'],
        'session': detect_session(candles[-1].get('timestamp', datetime.now())),
        'ohlc_last_10': candles[-10:],
        'metadata': {
            'rsi_14': rsi_val,
            'candles_checked': len(candles),
            'slope_norm': round(slope_norm, 2),  # Normalized slope 0-1
            'swing_count': len(swings.get('highs', [])) + len(swings.get('lows', [])),  # Total swing points
            'trend_consistent': trend_consistent,  # HH/HL or LH/LL consistent (no counter swings)
            'range_55': round(range_data['range'], 2)  # Range in USD
        }
    }


def determine_technique(chart_type: str, chart_detail: dict,
                        father: dict, twin: dict, candles: List[dict],
                        range_data: dict, swings: dict = None) -> str:
    """
    กำหนด technique candidate ตาม priority และ setup availability

    Strategy Section 1.7: unclear + father candle = mai_ruay
    ถ้าไม่มี setup ใดๆ → return 'skip'
    """

    if chart_type in ['uptrend', 'downtrend']:
        # Priority 1: Breakout box (ตามเจ้า)
        breakout = detect_breakout_box(candles, range_data, chart_type, swings)
        if breakout.get('found'):
            return 'breakout_follow'

        # Priority 2: Twin candle (ถ้ามี)
        if twin.get('found'):
            return 'twin_candle'

        # Priority 3: Father candle (ไม้รวย - ถ้าไม่มี twin)
        if father.get('found') and father.get('is_valid'):
            return 'mai_ruay'

        # ไม่มี setup → skip
        return 'skip'

    elif chart_type in ['sideway_down', 'sideway_up']:
        if twin.get('found'):
            return 'twin_candle'
        return 'skip'

    elif chart_type == 'mountain':
        # Priority 1: Father candle ลงถึงฐาน
        if father.get('found') and father.get('direction') == 'down':
            return 'mai_ruay'
        # Priority 2: Twin candle ที่ฐาน (detect_mountain already checks this)
        if twin.get('found') or chart_detail.get('twin_candle_base', {}).get('found'):
            return 'twin_candle'
        return 'skip'

    elif chart_type == 'unclear':
        # Strategy Section 1.7: unclear ยังเทรดได้ถ้ามี father candle
        if father.get('found') and father.get('is_valid'):
            return 'mai_ruay'
        return 'skip'

    return 'skip'


# ============================================================================
# MAIN CLASS
# ============================================================================

class G1PatternDetector:
    """
    G1 Multi-TF Visual Pattern Detector

    Usage:
        detector = G1PatternDetector()
        world_state = detector.scan_all_tf(candles_by_tf)
    """

    def __init__(self, config: Optional[dict] = None):
        """
        Args:
            config: {
                'verbose': bool,
                'timeframes': list (default: ['H4', 'H1', 'M30', 'M15', 'M5', 'M1'])
            }
        """
        self.config = config or {}
        self.verbose = self.config.get('verbose', False)
        self.timeframes = self.config.get('timeframes', TIMEFRAMES)
        logger.info(f"G1PatternDetector initialized (TFs: {self.timeframes})")

    def scan_all_tf(self, candles_by_tf: Dict[str, List[dict]]) -> dict:
        """
        Scan ทุก TF และเลือก best setup

        Args:
            candles_by_tf: {
                'H4': [candle1, candle2, ...],  # 55 แท่ง
                'H1': [...],
                ...
            }

        Returns:
            world_state dict (จาก best TF ที่เลือก)
        """
        tf_results = {}

        for tf in self.timeframes:
            candles = candles_by_tf.get(tf, [])
            if not candles or len(candles) < CANDLES_LOOKBACK:
                logger.warning(f"TF {tf}: not enough candles ({len(candles)} < {CANDLES_LOOKBACK})")
                continue

            # Detect pattern สำหรับ TF นี้
            range_data = calc_range(candles)
            world_state = build_world_state(candles, tf, range_data)

            tf_results[tf] = world_state

            if self.verbose:
                chart_type = world_state['chart_type']
                quality = world_state['quality']

                # แสดง trend angle ถ้ามี
                chart_detail = world_state.get('chart_detail', {})
                angle = chart_detail.get('slope_angle', None)

                if angle is not None and chart_type in ['uptrend', 'downtrend']:
                    logger.info(f"TF {tf}: {chart_type} (quality={quality:.2f}, angle={angle:.1f}°)")
                else:
                    logger.info(f"TF {tf}: {chart_type} (quality={quality:.2f})")

        # Select best setup
        best_setup = select_best_setup(tf_results)

        if best_setup['tf'] is None:
            # ทุก TF unclear
            return {
                'selected_tf': None,
                'chart_type': 'unclear',
                'quality': 0.0,
                'tf_results': tf_results,
                'skip_reason': 'all_tf_unclear'
            }

        # Return world_state ของ TF ที่เลือก + tf_results ทั้งหมด
        selected_tf = best_setup['tf']
        world_state = tf_results[selected_tf]
        world_state['selected_tf'] = selected_tf
        world_state['tf_results'] = tf_results  # เก็บไว้ดู context ทุก TF

        # Log selected TF
        if self.verbose:
            chart_type = world_state['chart_type']
            quality = world_state['quality']
            chart_detail = world_state.get('chart_detail', {})
            angle = chart_detail.get('slope_angle', None)

            if angle is not None and chart_type in ['uptrend', 'downtrend']:
                logger.info(f"✓ Selected {selected_tf} ({chart_type}) quality={quality:.2f}, angle={angle:.1f}°")
            else:
                logger.info(f"✓ Selected {selected_tf} ({chart_type}) quality={quality:.2f}")

        return world_state

    def scan_single_tf(self, candles: List[dict], timeframe: str = 'M5') -> dict:
        """
        Scan เฉพาะ TF เดียว (สำหรับ testing)

        Args:
            candles: list of 55 candles
            timeframe: TF name

        Returns:
            world_state dict
        """
        if len(candles) < CANDLES_LOOKBACK:
            logger.warning(f"Not enough candles: {len(candles)} < {CANDLES_LOOKBACK}")
            return {'chart_type': 'unclear', 'quality': 0.0}

        range_data = calc_range(candles)
        world_state = build_world_state(candles, timeframe, range_data)
        world_state['selected_tf'] = timeframe

        return world_state
