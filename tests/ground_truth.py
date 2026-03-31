"""
Ground Truth Test Cases

Test cases จากกราฟจริงและตัวอย่างจาก Strategy Document
ใช้สำหรับทดสอบว่า G1→G2→G3 pipeline ทำงานถูกต้อง

เป้าหมาย: pass ≥ 80% ก่อนเชื่อผล backtest
"""

from datetime import datetime, timedelta
import pandas as pd


def generate_uptrend_candles(base_price=3000, count=80):
    """สร้าง candles แบบ uptrend (Higher High & Higher Low)"""
    candles = []
    price = base_price
    time = datetime.now() - timedelta(minutes=5 * count)

    for i in range(count):
        # Uptrend: ราคาขึ้นทีละนิด
        price += (i % 10) * 0.5 + 1.0  # ขึ้นเฉลี่ย 1-6 points

        open_price = price + (i % 3 - 1) * 0.2
        high = price + abs(i % 5) * 0.3 + 0.5
        low = price - abs(i % 4) * 0.2
        close = price + (i % 3 - 1) * 0.3

        candles.append({
            'time': time,
            'open': round(open_price, 2),
            'high': round(high, 2),
            'low': round(low, 2),
            'close': round(close, 2),
            'tick_volume': 1000
        })
        time += timedelta(minutes=5)

    return candles


def generate_downtrend_candles(base_price=3100, count=80):
    """สร้าง candles แบบ downtrend (Lower High & Lower Low)"""
    candles = []
    price = base_price
    time = datetime.now() - timedelta(minutes=5 * count)

    for i in range(count):
        # Downtrend: ราคาลงทีละนิด
        price -= (i % 10) * 0.5 + 1.0

        open_price = price + (i % 3 - 1) * 0.2
        high = price + abs(i % 4) * 0.2
        low = price - abs(i % 5) * 0.3 - 0.5
        close = price - (i % 3 - 1) * 0.3

        candles.append({
            'time': time,
            'open': round(open_price, 2),
            'high': round(high, 2),
            'low': round(low, 2),
            'close': round(close, 2),
            'tick_volume': 1000
        })
        time += timedelta(minutes=5)

    return candles


def generate_mountain_candles(base_price=3000, count=80):
    """สร้าง candles แบบ mountain (ขึ้นแล้วลง)"""
    candles = []
    price = base_price
    time = datetime.now() - timedelta(minutes=5 * count)

    peak_index = count // 2

    for i in range(count):
        # ก่อน peak: ขึ้น, หลัง peak: ลง
        if i < peak_index:
            price += 2.0 + (i % 5) * 0.5
        else:
            price -= 1.5 + ((i - peak_index) % 5) * 0.3

        open_price = price
        high = price + abs(i % 4) * 0.3
        low = price - abs(i % 3) * 0.3
        close = price + (i % 3 - 1) * 0.2

        candles.append({
            'time': time,
            'open': round(open_price, 2),
            'high': round(high, 2),
            'low': round(low, 2),
            'close': round(close, 2),
            'tick_volume': 1000
        })
        time += timedelta(minutes=5)

    return candles


def generate_sideways_candles(base_price=3050, range_size=50, count=80):
    """สร้าง candles แบบ sideways (ออกข้างในกรอบ)"""
    candles = []
    time = datetime.now() - timedelta(minutes=5 * count)

    for i in range(count):
        # แกว่งในกรอบ
        price = base_price + (i % 10 - 5) * (range_size / 10)

        open_price = price
        high = price + abs(i % 3) * 0.5
        low = price - abs(i % 3) * 0.5
        close = price + (i % 3 - 1) * 0.3

        candles.append({
            'time': time,
            'open': round(open_price, 2),
            'high': round(high, 2),
            'low': round(low, 2),
            'close': round(close, 2),
            'tick_volume': 1000
        })
        time += timedelta(minutes=5)

    return candles


def generate_spike_reversal_candles(base_price=3050, spike_down=True, count=80):
    """สร้าง candles ที่มี spike reversal (ไม้รวย)"""
    candles = []
    time = datetime.now() - timedelta(minutes=5 * count)

    spike_index = count - 5  # Spike ใกล้ท้าย

    for i in range(count):
        if i < spike_index:
            # ก่อน spike: sideways
            price = base_price + (i % 10 - 5) * 0.5
            open_price = price
            high = price + 0.5
            low = price - 0.5
            close = price + (i % 3 - 1) * 0.2
        elif i == spike_index:
            # Spike candle
            if spike_down:
                # Spike ลง แล้ว reject (BUY signal)
                open_price = base_price
                high = base_price + 2
                low = base_price - 30  # ไส้ยาวลง
                close = base_price - 5  # ปิดใกล้ open
            else:
                # Spike ขึ้น แล้ว reject (SELL signal)
                open_price = base_price
                high = base_price + 30  # ไส้ยาวขึ้น
                low = base_price - 2
                close = base_price + 5  # ปิดใกล้ open
        else:
            # หลัง spike: recovery
            if spike_down:
                price = base_price + (i - spike_index) * 2
            else:
                price = base_price - (i - spike_index) * 2

            open_price = price
            high = price + 0.5
            low = price - 0.5
            close = price + 0.2

        candles.append({
            'time': time,
            'open': round(open_price, 2),
            'high': round(high, 2),
            'low': round(low, 2),
            'close': round(close, 2),
            'tick_volume': 1000
        })
        time += timedelta(minutes=5)

    return candles


def generate_h1_trend_candles(trend='bullish', count=50):
    """สร้าง H1 candles สำหรับ trend filter"""
    candles = []
    base_price = 3000
    time = datetime.now() - timedelta(hours=count)

    for i in range(count):
        if trend == 'bullish':
            price = base_price + i * 5
        elif trend == 'bearish':
            price = base_price - i * 5
        else:  # sideways
            price = base_price + (i % 10 - 5) * 2

        candles.append({
            'time': time,
            'open': round(price, 2),
            'high': round(price + 8, 2),
            'low': round(price - 8, 2),
            'close': round(price + (i % 3 - 1) * 2, 2),
            'tick_volume': 5000
        })
        time += timedelta(hours=1)

    return candles


# =============================================================================
# TEST CASES
# =============================================================================

GROUND_TRUTH_CASES = [
    # Case 1: ไม้รวย (Spike Reversal) - BUY
    {
        'id': 'GT001',
        'description': 'ไม้รวย M5, RSI 37.99 → A6_unclear, ไม้รวย, BUY',
        'm5_ohlcv': generate_spike_reversal_candles(base_price=3050, spike_down=True, count=80),
        'h1_candles': generate_h1_trend_candles('sideways', 50),
        'expected_condition': 'A6_unclear',
        'expected_pattern': 'ไม้รวย',
        'expected_action': 'BUY',
        'expected_rsi_range': (30, 45),  # Near oversold
    },

    # Case 2: ภูเขา (Mountain) - BUY
    {
        'id': 'GT002',
        'description': 'ภูเขา M5, RSI 44.61 → A3_mountain, แนวเด้ง, BUY',
        'm5_ohlcv': generate_mountain_candles(base_price=3000, count=80),
        'h1_candles': generate_h1_trend_candles('sideways', 50),
        'expected_condition': 'A3_mountain',
        'expected_pattern': 'แนวเด้ง',
        'expected_action': 'BUY',
        'expected_rsi_range': (40, 55),
    },

    # Case 3: เจ้าในแท่ง (Smart Money Follow) - BUY
    {
        'id': 'GT003',
        'description': 'เจ้าในแท่ง M5, RSI 65.36 → A1_uptrend, ตามเจ้า, BUY',
        'm5_ohlcv': generate_uptrend_candles(base_price=3000, count=80),
        'h1_candles': generate_h1_trend_candles('bullish', 50),
        'expected_condition': 'A1_uptrend',
        'expected_pattern': 'ตามเจ้า',
        'expected_action': 'BUY',
        'expected_rsi_range': (55, 70),  # Momentum zone
    },

    # Case 4: ในกรอบ (Sideways) - BUY
    {
        'id': 'GT004',
        'description': 'ในกรอบ M5, RSI 46.32 → A4_sideways_up, แนวเด้ง, BUY',
        'm5_ohlcv': generate_sideways_candles(base_price=3050, range_size=50, count=80),
        'h1_candles': generate_h1_trend_candles('sideways', 50),
        'expected_condition': 'A4_sideways_up',
        'expected_pattern': 'แนวเด้ง',
        'expected_action': 'BUY',
        'expected_rsi_range': (45, 55),  # Neutral zone OK for sideways
    },

    # Case 5: ตามเจ้าเฟิร์มสั้น (Follow downtrend) - SELL
    {
        'id': 'GT005',
        'description': 'ตามเจ้าเฟิร์มสั้น M5, RSI 39.00 → A2_downtrend, ตามเจ้า, SELL',
        'm5_ohlcv': generate_downtrend_candles(base_price=3100, count=80),
        'h1_candles': generate_h1_trend_candles('bearish', 50),
        'expected_condition': 'A2_downtrend',
        'expected_pattern': 'ตามเจ้า',
        'expected_action': 'SELL',
        'expected_rsi_range': (35, 45),
    },

    # Case 6: ไม้รวย SELL (Spike up rejection)
    {
        'id': 'GT006',
        'description': 'ไม้รวย spike ขึ้น, RSI 62 → A6_unclear, ไม้รวย, SELL',
        'm5_ohlcv': generate_spike_reversal_candles(base_price=3050, spike_down=False, count=80),
        'h1_candles': generate_h1_trend_candles('sideways', 50),
        'expected_condition': 'A6_unclear',
        'expected_pattern': 'ไม้รวย',
        'expected_action': 'SELL',
        'expected_rsi_range': (55, 70),
    },

    # Case 7: Sideways down - SELL
    {
        'id': 'GT007',
        'description': 'ไซเวย์ขาลง M5, RSI 58 → A5_sideways_down, แนวเด้ง, SELL',
        'm5_ohlcv': generate_sideways_candles(base_price=3000, range_size=60, count=80),
        'h1_candles': generate_h1_trend_candles('sideways', 50),
        'expected_condition': 'A5_sideways_down',
        'expected_pattern': 'แนวเด้ง',
        'expected_action': 'SELL',
        'expected_rsi_range': (50, 65),
    },

    # Case 8: Mountain - RSI extreme oversold
    {
        'id': 'GT008',
        'description': 'ภูเขาที่ฐาน, RSI 28 (extreme) → A3_mountain, แนวเด้ง, BUY',
        'm5_ohlcv': generate_mountain_candles(base_price=2950, count=80),
        'h1_candles': generate_h1_trend_candles('sideways', 50),
        'expected_condition': 'A3_mountain',
        'expected_pattern': 'แนวเด้ง',
        'expected_action': 'BUY',
        'expected_rsi_range': (25, 35),  # Extreme oversold
    },

    # Case 9: Uptrend pullback
    {
        'id': 'GT009',
        'description': 'Uptrend pullback, RSI 42 → A1_uptrend, แนวเด้ง, BUY',
        'm5_ohlcv': generate_uptrend_candles(base_price=3020, count=80),
        'h1_candles': generate_h1_trend_candles('bullish', 50),
        'expected_condition': 'A1_uptrend',
        'expected_pattern': 'แนวเด้ง',
        'expected_action': 'BUY',
        'expected_rsi_range': (36, 50),
    },

    # Case 10: Downtrend retest - SELL
    {
        'id': 'GT010',
        'description': 'Downtrend retest, RSI 56 → A2_downtrend, แนวเด้ง, SELL',
        'm5_ohlcv': generate_downtrend_candles(base_price=3080, count=80),
        'h1_candles': generate_h1_trend_candles('bearish', 50),
        'expected_condition': 'A2_downtrend',
        'expected_pattern': 'แนวเด้ง',
        'expected_action': 'SELL',
        'expected_rsi_range': (50, 65),
    },
]


def get_test_case(case_id: str):
    """Get test case by ID"""
    for case in GROUND_TRUTH_CASES:
        if case['id'] == case_id:
            return case
    return None


def get_all_test_cases():
    """Get all test cases"""
    return GROUND_TRUTH_CASES
