"""
Unit Tests for Twin Candle V4.3

ตรวจสอบ logic ของ:
1. is_swing_candle_pair — บทบาทที่ 1 (Swing Point)
2. is_entry_candle_pair — บทบาทที่ 2 (Entry Setup)
3. is_swing_high_v43 — Swing High Detection
4. is_swing_low_v43 — Swing Low Detection

Reference: XAUUSD_System_PromptV43.md
"""

import pytest
from utils.twin_candle_v43 import (
    is_swing_candle_pair,
    is_entry_candle_pair,
    is_swing_high_v43,
    is_swing_low_v43,
    find_technical_price_v43,
    calculate_mid_price
)


# ============================================================================
# TEST DATA HELPERS
# ============================================================================

def make_candle(open_price, high, low, close):
    """สร้าง candle dict"""
    return {"open": open_price, "high": high, "low": low, "close": close}


# ============================================================================
# ROLE 1: SWING CANDLE PAIR TESTS
# ============================================================================

def test_swing_pair_valid():
    """ห่าง 30pip, body 1.5%R55 → ผ่าน"""
    range55 = 50.0  # 50 USD = 5000 pip
    min_body_pip = 50  # 1% R55 = 50 pip = 0.50 USD

    c1 = make_candle(4800.0, 4801.0, 4799.5, 4800.6)  # body = 0.6 USD = 60 pip
    c2 = make_candle(4800.3, 4801.5, 4800.0, 4800.9)  # body = 0.6 USD = 60 pip
    # gap = |4800.6 - 4800.3| = 0.3 USD = 30 pip

    assert is_swing_candle_pair(c1, c2, range55) is True


def test_swing_pair_too_far():
    """ห่าง 60pip → ไม่ผ่าน"""
    range55 = 50.0

    c1 = make_candle(4800.0, 4801.0, 4799.5, 4800.6)
    c2 = make_candle(4801.2, 4802.0, 4801.0, 4801.8)  # gap = 60 pip

    assert is_swing_candle_pair(c1, c2, range55) is False


def test_swing_pair_body_too_small():
    """body 0.5%R55 → ไม่ผ่าน"""
    range55 = 50.0  # 1% = 50 pip

    c1 = make_candle(4800.0, 4800.3, 4799.9, 4800.2)  # body = 0.2 USD = 20 pip < 50 pip
    c2 = make_candle(4800.1, 4800.4, 4800.0, 4800.3)

    assert is_swing_candle_pair(c1, c2, range55) is False


def test_swing_pair_exact_threshold():
    """ห่าง 50pip พอดี, body 1% พอดี → ผ่าน"""
    range55 = 50.0  # 1% = 50 pip = 0.5 USD

    c1 = make_candle(4800.0, 4801.0, 4799.5, 4800.5)  # body = 0.5 USD
    c2 = make_candle(4801.0, 4802.0, 4800.5, 4801.5)  # body = 0.5 USD, gap = 50 pip

    assert is_swing_candle_pair(c1, c2, range55) is True


# ============================================================================
# ROLE 2: ENTRY CANDLE PAIR TESTS
# ============================================================================

def test_entry_pair_beauty_100():
    """ห่าง 10pip, body 8%R55 → beauty=100"""
    range55 = 50.0  # 7% = 350 pip = 3.5 USD

    c1 = make_candle(4800.0, 4804.5, 4799.5, 4804.0)  # body = 4.0 USD = 400 pip (8%R55)
    c2 = make_candle(4804.1, 4808.0, 4804.0, 4808.0)  # body = 3.9 USD, gap = 10 pip

    valid, beauty = is_entry_candle_pair(c1, c2, range55)
    assert valid is True
    assert beauty == 100


def test_entry_pair_beauty_90():
    """ห่าง 15pip, body 5.5%R55 → beauty=90"""
    range55 = 50.0  # 5% = 250 pip = 2.5 USD

    c1 = make_candle(4800.0, 4803.0, 4799.5, 4802.8)  # body = 2.8 USD = 280 pip (5.6%R55)
    c2 = make_candle(4802.95, 4806.0, 4802.5, 4805.8)  # body = 2.85 USD, gap = 15 pip

    valid, beauty = is_entry_candle_pair(c1, c2, range55)
    assert valid is True
    assert beauty == 90


def test_entry_pair_beauty_80():
    """ห่าง 18pip, body 4.5%R55 → beauty=80"""
    range55 = 50.0  # 4% = 200 pip = 2.0 USD

    c1 = make_candle(4800.0, 4802.5, 4799.5, 4802.3)  # body = 2.3 USD = 230 pip (4.6%R55)
    c2 = make_candle(4802.48, 4805.0, 4802.0, 4804.8)  # body = 2.32 USD, gap = 18 pip

    valid, beauty = is_entry_candle_pair(c1, c2, range55)
    assert valid is True
    assert beauty == 80


def test_entry_pair_beauty_60():
    """ห่าง 15pip, body 3.5%R55 → beauty=60"""
    range55 = 50.0  # 3% = 150 pip = 1.5 USD

    c1 = make_candle(4800.0, 4802.0, 4799.5, 4801.8)  # body = 1.8 USD = 180 pip (3.6%R55)
    c2 = make_candle(4801.95, 4804.0, 4801.5, 4803.8)  # body = 1.85 USD, gap = 15 pip

    valid, beauty = is_entry_candle_pair(c1, c2, range55)
    assert valid is True
    assert beauty == 60


def test_entry_pair_too_far():
    """ห่าง 25pip → ไม่ผ่าน"""
    range55 = 50.0

    c1 = make_candle(4800.0, 4804.0, 4799.5, 4803.5)  # body = 3.5 USD
    c2 = make_candle(4803.75, 4807.0, 4803.0, 4806.5)  # gap = 25 pip > 20

    valid, beauty = is_entry_candle_pair(c1, c2, range55)
    assert valid is False
    assert beauty == 0


def test_entry_pair_body_too_small():
    """ห่าง 10pip แต่ body < 3%R55 → ไม่ผ่าน"""
    range55 = 50.0  # 3% = 150 pip = 1.5 USD

    c1 = make_candle(4800.0, 4801.0, 4799.5, 4801.0)  # body = 1.0 USD = 100 pip < 150
    c2 = make_candle(4801.1, 4802.0, 4800.5, 4802.0)

    valid, beauty = is_entry_candle_pair(c1, c2, range55)
    assert valid is False
    assert beauty == 0


# ============================================================================
# SWING HIGH TESTS
# ============================================================================

def test_swing_high_valid():
    """mid > OC ทุกแท่งข้างเคียง → True"""
    range55 = 50.0

    # สร้าง 55 แท่ง โดยแท่ง 25-26 เป็น Swing High
    candles = []
    for i in range(55):
        if 22 <= i <= 24:  # ซ้าย 3 แท่ง (ต่ำกว่า)
            candles.append(make_candle(4800.0, 4801.0, 4799.5, 4800.5))
        elif i == 25:  # c1
            candles.append(make_candle(4800.5, 4803.0, 4800.0, 4802.5))  # body_hi = 4802.5
        elif i == 26:  # c2
            candles.append(make_candle(4802.4, 4804.0, 4802.0, 4803.5))  # body_hi = 4803.5
            # mid = (4802.5 + 4802.4) / 2 = 4802.45
        elif 27 <= i <= 28:  # ขวา 2 แท่ง (ต่ำกว่า)
            candles.append(make_candle(4802.0, 4802.3, 4801.5, 4802.2))
        else:
            candles.append(make_candle(4800.0, 4801.0, 4799.5, 4800.5))

    assert is_swing_high_v43(candles, 25, range55) is True


def test_swing_high_blocked_left():
    """แท่งซ้ายสูงกว่า mid → False"""
    range55 = 50.0

    candles = []
    for i in range(55):
        if i == 22:  # ซ้าย 3 แท่ง - แท่งนี้สูงกว่า mid
            candles.append(make_candle(4802.0, 4803.0, 4801.5, 4802.8))  # body_hi = 4802.8 > mid
        elif 23 <= i <= 24:
            candles.append(make_candle(4800.0, 4801.0, 4799.5, 4800.5))
        elif i == 25:  # c1
            candles.append(make_candle(4800.5, 4803.0, 4800.0, 4802.5))
        elif i == 26:  # c2
            candles.append(make_candle(4802.4, 4804.0, 4802.0, 4803.5))
            # mid = 4802.45
        elif 27 <= i <= 28:
            candles.append(make_candle(4802.0, 4802.3, 4801.5, 4802.2))
        else:
            candles.append(make_candle(4800.0, 4801.0, 4799.5, 4800.5))

    assert is_swing_high_v43(candles, 25, range55) is False


def test_swing_high_blocked_right():
    """แท่งขวาสูงกว่า mid → False"""
    range55 = 50.0

    candles = []
    for i in range(55):
        if 22 <= i <= 24:
            candles.append(make_candle(4800.0, 4801.0, 4799.5, 4800.5))
        elif i == 25:  # c1
            candles.append(make_candle(4800.5, 4803.0, 4800.0, 4802.5))
        elif i == 26:  # c2
            candles.append(make_candle(4802.4, 4804.0, 4802.0, 4803.5))
            # mid = 4802.45
        elif i == 27:  # ขวา 1 - แท่งนี้สูงกว่า mid
            candles.append(make_candle(4802.5, 4803.5, 4802.0, 4803.0))  # body_hi = 4803.0 > mid
        elif i == 28:
            candles.append(make_candle(4802.0, 4802.3, 4801.5, 4802.2))
        else:
            candles.append(make_candle(4800.0, 4801.0, 4799.5, 4800.5))

    assert is_swing_high_v43(candles, 25, range55) is False


# ============================================================================
# SWING LOW TESTS
# ============================================================================

def test_swing_low_valid():
    """mid < OC ทุกแท่งข้างเคียง → True"""
    range55 = 50.0  # 1% = 50 pip = 0.5 USD

    candles = []
    for i in range(55):
        if 22 <= i <= 24:  # ซ้าย 3 แท่ง (สูงกว่า)
            candles.append(make_candle(4802.0, 4803.0, 4801.5, 4802.5))
        elif i == 25:  # c1 - body ≥ 0.5 USD
            candles.append(make_candle(4801.0, 4802.0, 4800.0, 4800.5))  # body = 0.5 USD = 50 pip ✅
        elif i == 26:  # c2 - body ≥ 0.5 USD
            candles.append(make_candle(4800.6, 4801.5, 4800.0, 4801.2))  # body = 0.6 USD = 60 pip ✅
            # mid = (4800.5 + 4800.6) / 2 = 4800.55
        elif 27 <= i <= 28:  # ขวา 2 แท่ง (สูงกว่า)
            candles.append(make_candle(4801.0, 4802.0, 4800.5, 4801.5))
        else:
            candles.append(make_candle(4802.0, 4803.0, 4801.5, 4802.5))

    assert is_swing_low_v43(candles, 25, range55) is True


def test_swing_low_blocked_left():
    """แท่งซ้ายต่ำกว่า mid → False"""
    range55 = 50.0

    candles = []
    for i in range(55):
        if i == 22:  # ซ้าย 3 - แท่งนี้ต่ำกว่า mid
            candles.append(make_candle(4801.0, 4801.5, 4800.0, 4800.3))  # body_lo = 4800.3 < mid
        elif 23 <= i <= 24:
            candles.append(make_candle(4802.0, 4803.0, 4801.5, 4802.5))
        elif i == 25:  # c1
            candles.append(make_candle(4801.5, 4802.0, 4800.0, 4800.5))
        elif i == 26:  # c2
            candles.append(make_candle(4800.6, 4801.5, 4800.0, 4801.0))
            # mid = 4800.55
        elif 27 <= i <= 28:
            candles.append(make_candle(4801.0, 4802.0, 4800.5, 4801.5))
        else:
            candles.append(make_candle(4802.0, 4803.0, 4801.5, 4802.5))

    assert is_swing_low_v43(candles, 25, range55) is False


# ============================================================================
# HELPER FUNCTION TESTS
# ============================================================================

def test_find_technical_price():
    """Technical price = body_lo ที่ต่ำกว่า"""
    c1 = make_candle(4800.0, 4802.0, 4799.5, 4801.5)  # body_lo = 4800.0
    c2 = make_candle(4801.6, 4803.0, 4801.0, 4802.5)  # body_lo = 4801.6

    tech_price = find_technical_price_v43(c1, c2)
    assert tech_price == 4800.0  # min(4800.0, 4801.6)


def test_calculate_mid_price():
    """mid = (C1 + O2) ÷ 2"""
    c1 = make_candle(4800.0, 4802.0, 4799.5, 4801.5)  # close = 4801.5
    c2 = make_candle(4801.6, 4803.0, 4801.0, 4802.5)  # open = 4801.6

    mid = calculate_mid_price(c1, c2)
    assert mid == pytest.approx((4801.5 + 4801.6) / 2, abs=0.01)


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
