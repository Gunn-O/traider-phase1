# Pattern Detection Spec v1.0
> สำหรับ G1 Visual Pattern Detector
> อ้างอิง: XAUUSD_AI_Trading_System.md v2.0
> หน่วย: 1 pip = 0.01 USD | 100 pip = 1 USD

---

## ข้อกำหนดพื้นฐาน

```python
CANDLES_LOOKBACK = 55       # จำนวนแท่งที่ใช้วิเคราะห์ทุกครั้ง
SCREEN_X = 5.7              # หน่วยแกน X (สัดส่วนหน้าจอ)
SCREEN_Y = 7.4              # หน่วยแกน Y (สัดส่วนหน้าจอ)
TARGET_SLOPE_DEG = 47.5     # ความชันอ้างอิง Uptrend/Downtrend (45-50°)
MIN_TWIN_CANDLE_BODY = 0.05 # แท่งคู่: เนื้อเทียนต้องหนา ≥ 5% Range
MAX_TWIN_CANDLE_GAP = 10    # แท่งคู่: Open/Close ห่างกันได้ไม่เกิน 10 pip
TIMEFRAMES = ['H4','H1','M30','M15','M5','M1']
```

---

## Step 0 — คำนวณ Range 55 แท่ง

```python
def calc_range(candles: list) -> dict:
    """
    candles: list of 55 candles (newest last)
    return: {
        high: float,    # High สูงสุดใน 55 แท่ง
        low: float,     # Low ต่ำสุดใน 55 แท่ง
        range: float,   # high - low (USD)
        range_pip: int  # range × 100 (pip)
    }
    """
    high = max(c['high'] for c in candles)
    low = min(c['low'] for c in candles)
    range_usd = high - low
    return {
        'high': high,
        'low': low,
        'range': range_usd,
        'range_pip': int(range_usd * 100)
    }
```

---

## Step 1 — คำนวณความชัน (Slope)

### หลักการแปลงองศาเป็นตัวเลข

```
หน้าจอ: แกน X = 5.7 หน่วย (55 แท่ง), แกน Y = 7.4 หน่วย (100% Range)
ความชัน 45° บนหน้าจอ = tan(45°) = 1.0
แต่ Y scale ≠ X scale → ต้องแปลง

slope_screen = (Δprice / range) / (Δcandles / 55) × (SCREEN_X / SCREEN_Y)
angle_deg = atan(slope_screen) × (180 / π)

เป้าหมาย: angle_deg อยู่ระหว่าง 45-50°
```

```python
import math

def calc_slope_angle(price_start: float, price_end: float,
                     candle_start: int, candle_end: int,
                     range_usd: float) -> float:
    """
    คำนวณมุมความชันของเส้นแนวโน้มบนหน้าจอ
    return: องศา (0-90)
    """
    delta_price = abs(price_end - price_start)
    delta_candles = abs(candle_end - candle_start)
    if delta_candles == 0 or range_usd == 0:
        return 0.0

    # normalize ให้อยู่ใน screen coordinate
    norm_y = (delta_price / range_usd)           # 0-1
    norm_x = (delta_candles / 55)                # 0-1
    slope_screen = (norm_y / norm_x) * (SCREEN_X / SCREEN_Y)
    angle = math.degrees(math.atan(slope_screen))
    return round(angle, 1)

def is_good_slope(angle: float) -> bool:
    """ความชัน 45-50 องศา = Uptrend/Downtrend ที่ดี"""
    return 43.0 <= angle <= 52.0  # ±3° tolerance

def slope_quality(angle: float) -> float:
    """
    ให้คะแนน 0-1 ตามความใกล้เคียง 47.5°
    1.0 = ตรง 47.5° | 0.0 = ห่าง > 20°
    """
    diff = abs(angle - TARGET_SLOPE_DEG)
    if diff > 20:
        return 0.0
    return round(1.0 - (diff / 20), 2)
```

---

## Step 2 — ตรวจ HH/HL Pattern (Uptrend) และ LH/LL (Downtrend)

```python
def find_swing_points(candles: list, window: int = 3) -> dict:
    """
    หา swing highs และ swing lows จาก 55 แท่ง
    window: จำนวนแท่งรอบข้างที่ต้องสูง/ต่ำกว่า
    return: {
        highs: [(index, price), ...],
        lows: [(index, price), ...]
    }
    """
    highs, lows = [], []
    for i in range(window, len(candles) - window):
        # swing high: สูงกว่าทุกแท่งในระยะ window
        if all(candles[i]['high'] >= candles[j]['high']
               for j in range(i-window, i+window+1) if j != i):
            highs.append((i, candles[i]['high']))
        # swing low: ต่ำกว่าทุกแท่งในระยะ window
        if all(candles[i]['low'] <= candles[j]['low']
               for j in range(i-window, i+window+1) if j != i):
            lows.append((i, candles[i]['low']))
    return {'highs': highs, 'lows': lows}


def check_hh_hl(swing_points: dict, min_count: int = 3) -> dict:
    """
    ตรวจ Higher High + Higher Low (Uptrend)
    return: {
        is_uptrend: bool,
        hh_count: int,     # จำนวน HH ที่เจอ
        hl_count: int,     # จำนวน HL ที่เจอ
        consecutive: bool  # HH/HL ต่อเนื่องโดยไม่มีสวนทิศ
    }
    """
    highs = [p[1] for p in swing_points['highs']]
    lows = [p[1] for p in swing_points['lows']]

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


def check_lh_ll(swing_points: dict, min_count: int = 3) -> dict:
    """ตรวจ Lower High + Lower Low (Downtrend) — กลับทาง check_hh_hl"""
    highs = [p[1] for p in swing_points['highs']]
    lows = [p[1] for p in swing_points['lows']]

    lh_count = sum(1 for i in range(1, len(highs)) if highs[i] < highs[i-1])
    ll_count = sum(1 for i in range(1, len(lows)) if lows[i] < lows[i-1])
    has_hh = any(highs[i] > highs[i-1] for i in range(1, len(highs)))

    return {
        'is_downtrend': lh_count >= min_count and ll_count >= min_count and not has_hh,
        'lh_count': lh_count,
        'll_count': ll_count,
        'consecutive': not has_hh
    }
```

---

## Step 3 — Detect Chart Type

### 3.1 Uptrend

```python
def detect_uptrend(candles: list, range_data: dict) -> dict:
    """
    return: {
        detected: bool,
        quality: float,     # 0.0-1.0
        slope_angle: float,
        hh_hl: dict
    }
    """
    swings = find_swing_points(candles)
    hh_hl = check_hh_hl(swings)
    if not hh_hl['is_uptrend']:
        return {'detected': False, 'quality': 0.0}

    # คำนวณความชันจาก Low แรก → High ล่าสุด
    first_low_idx = swings['lows'][0][0] if swings['lows'] else 0
    last_high_idx = swings['highs'][-1][0] if swings['highs'] else 54
    first_low_price = swings['lows'][0][1] if swings['lows'] else candles[0]['low']
    last_high_price = swings['highs'][-1][1] if swings['highs'] else candles[-1]['high']

    angle = calc_slope_angle(first_low_price, last_high_price,
                             first_low_idx, last_high_idx,
                             range_data['range'])

    slope_q = slope_quality(angle)
    continuity_q = 1.0 if hh_hl['consecutive'] else 0.5
    count_q = min(hh_hl['hh_count'] / 5, 1.0)  # 5+ HH = perfect

    quality = round((slope_q * 0.5) + (continuity_q * 0.3) + (count_q * 0.2), 2)

    return {
        'detected': quality >= 0.5,
        'quality': quality,
        'slope_angle': angle,
        'hh_hl': hh_hl
    }
```

### 3.2 Downtrend

```python
def detect_downtrend(candles: list, range_data: dict) -> dict:
    """กลับทาง detect_uptrend ทุกอย่าง"""
    swings = find_swing_points(candles)
    lh_ll = check_lh_ll(swings)
    if not lh_ll['is_downtrend']:
        return {'detected': False, 'quality': 0.0}

    first_high_idx = swings['highs'][0][0] if swings['highs'] else 0
    last_low_idx = swings['lows'][-1][0] if swings['lows'] else 54
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
```

### 3.3 Sideway Press Down / Up

```python
def detect_sideway(candles: list, range_data: dict) -> dict:
    """
    ตรวจไซเวย์กดลง และไซเวย์ยกขึ้น
    return: {
        detected: bool,
        type: 'press_down' | 'press_up' | None,
        quality: float,
        impulse_candles: int,   # จำนวนแท่งขาพุ่ง
        impulse_pct: float,     # % Range ที่ขาพุ่งครอบคลุม
        box_high: float,        # กรอบบน
        box_low: float,         # กรอบล่าง
        box_pct: float,         # ขนาดกรอบ % Range
        current_position: str   # 'near_top' | 'near_bottom' | 'middle'
    }
    """
    R = range_data['range']
    # หาขาพุ่ง: กลุ่มแท่ง 3-10 แท่งที่เคลื่อน 80-100% Range
    # ตรวจจากแท่งเก่าไปใหม่
    impulse_result = find_impulse_leg(candles, R)
    if not impulse_result['found']:
        return {'detected': False, 'type': None, 'quality': 0.0}

    imp = impulse_result
    # กรอบ Sideway ต้องมีขนาด ≤ 50% Range
    remaining = candles[imp['end_idx']:]
    if len(remaining) < 5:
        return {'detected': False, 'type': None, 'quality': 0.0}

    box_high = max(c['high'] for c in remaining)
    box_low = min(c['low'] for c in remaining)
    box_size = box_high - box_low
    box_pct = box_size / R

    if box_pct > 0.50:  # กรอบใหญ่เกิน 50% = ไม่ชัด
        return {'detected': False, 'type': None, 'quality': 0.0}

    # ตรวจว่าอยู่ส่วนไหนของ Range
    current_price = candles[-1]['close']
    box_position_pct = (current_price - range_data['low']) / R

    sideway_type = 'press_down' if imp['direction'] == 'down' else 'press_up'

    # คุณภาพ: ขาพุ่งเต็ม 100% + กรอบชัด + ตำแหน่งถูก
    impulse_q = min(imp['pct'] / 0.8, 1.0)     # 80%+ = full score
    box_q = 1.0 - (box_pct / 0.5)              # กรอบเล็กยิ่งดี
    quality = round((impulse_q * 0.6) + (box_q * 0.4), 2)

    # ตำแหน่งราคาปัจจุบันในกรอบ
    if current_price >= box_high - (box_size * 0.15):
        position = 'near_top'
    elif current_price <= box_low + (box_size * 0.15):
        position = 'near_bottom'
    else:
        position = 'middle'

    return {
        'detected': quality >= 0.5,
        'type': sideway_type,
        'quality': quality,
        'impulse_candles': imp['count'],
        'impulse_pct': imp['pct'],
        'box_high': box_high,
        'box_low': box_low,
        'box_pct': box_pct,
        'current_position': position
    }


def find_impulse_leg(candles: list, range_usd: float) -> dict:
    """
    หากลุ่มแท่ง 3-10 แท่งที่เคลื่อน 60-100% ของ Range ทิศทางเดียว
    """
    for start in range(len(candles) - 10):
        for count in range(3, 11):
            end = start + count
            if end >= len(candles):
                break
            group = candles[start:end]

            # ทุกแท่งต้องเป็นสีเดียวกัน (bullish หรือ bearish)
            is_bearish = all(c['close'] < c['open'] for c in group)
            is_bullish = all(c['close'] > c['open'] for c in group)

            if not (is_bearish or is_bullish):
                continue

            price_move = abs(group[-1]['close'] - group[0]['open'])
            pct = price_move / range_usd

            if pct >= 0.60:  # เคลื่อน 60%+ ของ Range
                return {
                    'found': True,
                    'start_idx': start,
                    'end_idx': end,
                    'count': count,
                    'pct': round(pct, 2),
                    'direction': 'down' if is_bearish else 'up'
                }
    return {'found': False}
```

### 3.4 Mountain

```python
def detect_mountain(candles: list, range_data: dict) -> dict:
    """
    ตรวจภูเขา: ขึ้น-ยอด-ลง ใน 55 แท่ง
    เงื่อนไข: ความสูง > 50% Range, ลงกลับฐานภายใน 55 แท่ง
    return: {
        detected: bool,
        quality: float,
        peak_idx: int,
        peak_price: float,
        left_base_price: float,     # ฐานซ้าย
        right_base_price: float,    # ฐานขวา (ราคาปัจจุบันใกล้ฐาน)
        height_pct: float,          # ความสูง % Range
        return_candles: int,        # แท่งที่ใช้วกกลับฐาน
        twin_candle_base: dict,     # แท่งคู่ที่ฐานซ้าย
        tolerance_ok: bool          # ราคาปัจจุบันอยู่ใน tolerance ฐาน
    }
    """
    R = range_data['range']
    swings = find_swing_points(candles)

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
    if height_pct <= 0.50:  # ต้องสูงกว่า 50% Range
        return {'detected': False, 'quality': 0.0}

    # ตรวจว่าราคาปัจจุบันกลับมาใกล้ฐานซ้ายแล้วหรือยัง
    current_price = candles[-1]['close']
    tolerance = min(R * 0.05, 3.0)  # 5% Range หรือ 300 pip (3 USD)
    near_base = abs(current_price - left_base_price) <= tolerance

    # แท่งที่ใช้วกกลับ (นับจากยอดถึงปัจจุบัน)
    return_candles = len(candles) - 1 - peak_idx

    # หาแท่งคู่ที่ฐานซ้าย
    twin = find_twin_candle(candles, left_base_idx, left_base_price, R, 'base')

    # Quality scoring
    height_q = min(height_pct / 1.0, 1.0)           # 100% Range = perfect
    speed_q = 1.0 if return_candles <= 40 else max(0, 1.0 - (return_candles-40)/15)
    shape_q = calc_mountain_shape(candles, left_base_idx, peak_idx, R)

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


def calc_mountain_shape(candles, base_idx, peak_idx, range_usd) -> float:
    """
    คะแนนรูปทรงสามเหลี่ยม: 1.0 = สมมาตรสมบูรณ์
    วัดจาก |ขาขึ้น - ขาลง| / max(ขาขึ้น, ขาลง)
    """
    left_len = peak_idx - base_idx
    right_len = len(candles) - 1 - peak_idx
    if left_len == 0 or right_len == 0:
        return 0.0
    symmetry = 1.0 - abs(left_len - right_len) / max(left_len, right_len)
    return round(symmetry, 2)
```

---

## Step 4 — ตรวจแท่งคู่ (Twin Candle)

```python
def find_twin_candle(candles: list, search_start: int,
                     near_price: float, range_usd: float,
                     context: str = 'general') -> dict:
    """
    หาแท่งคู่ใกล้ near_price
    เงื่อนไข:
    - Open/Close ของ 2 แท่ง ห่างกัน ≤ 10 pip (0.10 USD)
    - เนื้อเทียนแต่ละแท่ง ≥ 5% Range
    return: {
        found: bool,
        candle1_idx: int,
        candle2_idx: int,
        technical_price: float,   # ราคาจุดเทคนิค (เนื้อล่าง/บน)
        body_pct: float           # ขนาดเนื้อเทียน % Range
    }
    """
    min_body = range_usd * MIN_TWIN_CANDLE_BODY  # 5% Range
    max_gap = 0.10  # 10 pip = 0.10 USD

    search_range = range(max(0, search_start-5),
                         min(len(candles)-1, search_start+10))

    for i in search_range:
        for j in [i+1, i-1]:
            if j < 0 or j >= len(candles):
                continue
            c1, c2 = candles[i], candles[j]

            body1 = abs(c1['close'] - c1['open'])
            body2 = abs(c2['close'] - c2['open'])

            if body1 < min_body or body2 < min_body:
                continue

            # gap ระหว่าง 2 แท่ง
            levels1 = [c1['open'], c1['close']]
            levels2 = [c2['open'], c2['close']]
            min_gap = min(abs(a-b) for a in levels1 for b in levels2)

            if min_gap <= max_gap:
                # จุดเทคนิค = เนื้อล่างของแท่งคู่
                tech_price = min(min(c1['open'], c1['close']),
                                min(c2['open'], c2['close']))
                return {
                    'found': True,
                    'candle1_idx': i,
                    'candle2_idx': j,
                    'technical_price': tech_price,
                    'body_pct': round(min(body1, body2) / range_usd, 3)
                }

    return {'found': False}
```

---

## Step 5 — ตรวจแท่งพ่อ (Father Candle สำหรับไม้รวย)

```python
def detect_father_candle(candles: list, range_data: dict) -> dict:
    """
    หาแท่งพ่อ: 1-5 แท่งที่เคลื่อน 60-100% Range ทิศทางเดียว
    ตรวจจากแท่งล่าสุดย้อนหลัง
    return: {
        found: bool,
        quality: float,
        start_idx: int,
        end_idx: int,           # แท่งสุดท้ายของแท่งพ่อ (ล่าสุด)
        direction: 'up'|'down',
        pct_range: float,       # % ของ Range ที่เคลื่อน
        mother_candle: dict,    # แท่งแม่ (แท่งถัดจากพ่อ)
        is_valid: bool          # มีแท่งแม่และขนาดถูกต้อง
    }
    """
    R = range_data['range']

    # ตรวจย้อนหลังจากแท่งล่าสุด
    for end_idx in range(len(candles)-2, len(candles)-15, -1):
        for count in range(1, 6):  # 1-5 แท่ง
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

            if pct < 0.60:  # ต้องเคลื่อน 60%+ ของ Range
                continue

            direction = 'down' if is_bearish else 'up'

            # ตรวจแท่งแม่ (แท่งถัดจากแท่งพ่อ)
            mother_idx = end_idx + 1
            if mother_idx >= len(candles):
                # แท่งพ่อพึ่งจบ ยังไม่มีแม่
                mother = {'found': False, 'valid': False}
            else:
                mother = check_mother_candle(
                    candles[mother_idx], group[-1], direction, R
                )

            # Quality
            pct_q = min((pct - 0.6) / 0.4, 1.0)   # 100% = 1.0
            count_q = 1.0 - ((count-1) / 4 * 0.3)  # แท่งเดียว = 1.0
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
    - ขนาดเนื้อ 5-40% ของแท่งพ่อ (5-20% สวย, 20-30% พอรับได้, 30-40% ไม่สวย)
    """
    father_body = abs(last_father['close'] - last_father['open'])
    mother_body = abs(mother['close'] - mother['open'])  # ไม่รวมไส้

    if father_body == 0:
        return {'found': True, 'valid': False}

    # ปิดสวนทิศ
    if father_direction == 'down':
        reversed_close = mother['close'] > mother['open']  # bullish
    else:
        reversed_close = mother['close'] < mother['open']  # bearish

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

    # จุดเทคนิค = Close พ่อ ≈ Open แม่
    technical_price = last_father['close']

    return {
        'found': True,
        'valid': valid,
        'reversed_close': reversed_close,
        'body_ratio': round(body_ratio, 3),
        'beauty': beauty,
        'technical_price': technical_price
    }
```

---

## Step 6 — ตรวจกรอบตามเจ้า (Breakout Box)

```python
def detect_breakout_box(candles: list, range_data: dict,
                        chart_type: str) -> dict:
    """
    หากรอบเล็กๆ ระหว่างเทรน สำหรับ Technique ตามเจ้า
    เงื่อนไข: กรอบบน-ล่าง ≤ 35% ของ Range 55 แท่ง
    return: {
        found: bool,
        box_high: float,
        box_low: float,
        box_pct: float,
        breakout_direction: 'up'|'down'|None
    }
    """
    if chart_type not in ['uptrend', 'downtrend', 'mountain']:
        return {'found': False}

    R = range_data['range']
    max_box = R * 0.35  # กรอบต้องไม่เกิน 35% Range

    # มองแท่ง 5-15 แท่งล่าสุด หาพื้นที่แออัด
    recent = candles[-15:]
    recent_high = max(c['high'] for c in recent)
    recent_low = min(c['low'] for c in recent)
    box_size = recent_high - recent_low

    if box_size > max_box:
        return {'found': False}

    # ตรวจ breakout direction จากแท่งล่าสุด
    last = candles[-1]
    if last['close'] > recent_high - (box_size * 0.1):
        breakout = 'up'
    elif last['close'] < recent_low + (box_size * 0.1):
        breakout = 'down'
    else:
        breakout = None

    return {
        'found': True,
        'box_high': recent_high,
        'box_low': recent_low,
        'box_pct': round(box_size / R, 2),
        'breakout_direction': breakout
    }
```

---

## Step 7 — Re-classify ไซเวย์

```python
def check_sideway_still_valid(candles: list, sideway_state: dict,
                               range_data: dict) -> dict:
    """
    ตรวจว่าไซเวย์ยังมีผลอยู่ไหม
    Re-classify เป็น 'unclear' ถ้า:
    1. ขาพุ่งเดิมเลื่อนออกนอก 55 แท่ง
    2. ราคาหลุดกรอบและไม่กลับเข้ามา (2 แท่ง close นอกกรอบ)
    """
    impulse_end_idx = sideway_state.get('impulse_end_idx', 0)
    candles_since_impulse = len(candles) - impulse_end_idx

    # กรณี 1: ขาพุ่งเลื่อนออกจาก 55 แท่ง
    if candles_since_impulse >= 55:
        return {'still_valid': False, 'reason': 'impulse_out_of_window'}

    # กรณี 2: ราคาหลุดกรอบ
    box_high = sideway_state['box_high']
    box_low = sideway_state['box_low']
    last_2 = candles[-2:]
    both_above = all(c['close'] > box_high for c in last_2)
    both_below = all(c['close'] < box_low for c in last_2)

    if both_above or both_below:
        return {'still_valid': False, 'reason': 'box_broken'}

    return {'still_valid': True}
```

---

## Step 8 — Setup Priority และ Chart Quality

```python
SETUP_PRIORITY = {
    # chart_type: priority (ต่ำ = สำคัญกว่า)
    'uptrend': 1,
    'downtrend': 1,
    'sideway_down': 2,
    'sideway_up': 2,
    'mountain': 3,
    'unclear': 4
}

TECHNIQUE_PRIORITY = {
    # เมื่อ chart type ชัดแล้ว
    'twin_candle': 1,   # ในกรอบ/แท่งคู่
    'breakout_follow': 2,  # ตามเจ้า
    'mai_ruay': 3,      # ไม้รวย
    'support_bounce': 4  # แนวเด้ง (ยังไม่ใช้ Phase I)
}


def select_best_setup(tf_results: dict) -> dict:
    """
    เลือก TF และ Setup ที่ดีที่สุดจาก 6 TF
    กฎ:
    1. เลือก chart_type ที่มี priority ต่ำสุด (ชัดสุด)
    2. ถ้า quality เท่ากัน → เลือก TF ใหญ่กว่า
    3. ถ้าสัญญาณทิศทางตรงข้าม → เลือกอันที่ quality สูงกว่า
    4. สัญญาณที่เกิดก่อน (เก่ากว่า) มี priority สูงกว่าถ้า quality ใกล้กัน (<0.1 ต่าง)

    tf_results: {
        'H4': {'chart_type': str, 'quality': float, 'technique': str, ...},
        'H1': {...}, 'M30': {...}, 'M15': {...}, 'M5': {...}, 'M1': {...}
    }
    """
    TF_SIZE = {'H4': 6, 'H1': 5, 'M30': 4, 'M15': 3, 'M5': 2, 'M1': 1}

    valid = {tf: r for tf, r in tf_results.items()
             if r.get('chart_type') != 'unclear' and r.get('quality', 0) >= 0.5}

    if not valid:
        return {'tf': None, 'chart_type': 'unclear', 'quality': 0.0}

    # Sort: priority ASC, quality DESC, TF_SIZE DESC
    def sort_key(item):
        tf, r = item
        prio = SETUP_PRIORITY.get(r['chart_type'], 99)
        return (prio, -r['quality'], -TF_SIZE[tf])

    sorted_results = sorted(valid.items(), key=sort_key)
    best_tf, best_result = sorted_results[0]

    return {
        'tf': best_tf,
        **best_result
    }
```

---

## Step 9 — World State Output

```python
def build_world_state(candles_by_tf: dict, current_tf: str) -> dict:
    """
    รวม output ทั้งหมดเป็น world_state JSON
    ส่งให้ G2 และ G3a
    """
    candles = candles_by_tf[current_tf]
    R = calc_range(candles)
    swings = find_swing_points(candles)

    # Detect ทุก chart type
    uptrend = detect_uptrend(candles, R)
    downtrend = detect_downtrend(candles, R)
    sideway = detect_sideway(candles, R)
    mountain = detect_mountain(candles, R)
    father = detect_father_candle(candles, R)

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
        chart_type = sideway['type']  # press_down or press_up
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
    technique = determine_technique(chart_type, chart_detail, father, R)

    # Metadata (ไม่ใช้ตัดสิน แต่เก็บไว้)
    import ta
    closes = [c['close'] for c in candles]
    rsi_val = calc_rsi(closes, 14)

    return {
        'timeframe': current_tf,
        'chart_type': chart_type,
        'chart_quality': quality,
        'chart_detail': chart_detail,
        'technique_candidate': technique,
        'range': {
            'high': R['high'],
            'low': R['low'],
            'usd': R['range'],
            'pip': R['range_pip']
        },
        'swing_points': swings,
        'father_candle': father,
        'current_price': candles[-1]['close'],
        'session': detect_session(candles[-1]['timestamp']),
        'metadata': {
            'rsi_14': rsi_val,
            'candles_checked': len(candles)
        }
    }


def determine_technique(chart_type: str, chart_detail: dict,
                        father: dict, range_usd: float) -> str:
    """กำหนด technique candidate ตาม priority"""
    if chart_type in ['uptrend', 'downtrend']:
        # ดู breakout box ก่อน (ตามเจ้า)
        if chart_detail.get('breakout_box', {}).get('found'):
            return 'breakout_follow'
        return 'twin_candle'

    elif chart_type in ['sideway_down', 'sideway_up']:
        return 'twin_candle'  # ใช้แท่งคู่กรอบเสมอ

    elif chart_type == 'mountain':
        if father.get('found') and father.get('direction') == 'down':
            return 'mai_ruay'  # ถ้าพ่อลงถึงฐาน
        return 'twin_candle'

    elif chart_type == 'unclear':
        if father.get('found') and father.get('is_valid'):
            return 'mai_ruay'
        return 'skip'

    return 'skip'
```

---

## หมายเหตุการ Implement

1. `calc_rsi()` ใช้จาก `utils/indicators.py` เดิมได้
2. `detect_session()` ใช้จาก `agents/g1_signal_logic.py` เดิมได้
3. แต่ละ TF ต้องเรียก `build_world_state()` แยกกัน แล้วส่งให้ `select_best_setup()`
4. ใน **Winrate Test Mode** ใช้ `lot = 0.01` ทุกไม้ ไม่คำนวณตาม 4.4
5. `find_swing_points()` window=3 เหมาะสำหรับ M5, อาจต้องปรับเป็น 5 สำหรับ H4
