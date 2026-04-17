"""
Unit Tests for G3PythonDecision Engine

Tests all 4 techniques + edge cases.

Run:
    pytest tests/test_g3_python_decision.py -v
"""

import pytest
from agents.g3_python_decision import G3PythonDecision


@pytest.fixture
def engine():
    """Create engine instance."""
    return G3PythonDecision(config={'verbose': False})


@pytest.fixture
def mock_portfolio():
    """Mock portfolio state."""
    return {
        'active_plan_id': '',
        'consecutive_loss': 0,
        'total_loss_pct': 0.0,
        'news_flag': False,
        'last_technical_price': 0.0,
        'last_plan_chart_type': ''
    }


@pytest.fixture
def mock_ohlc():
    """Mock last 10 candles."""
    return [
        {'open': 4700, 'high': 4705, 'low': 4698, 'close': 4703},
        {'open': 4703, 'high': 4708, 'low': 4700, 'close': 4706},
        {'open': 4706, 'high': 4712, 'low': 4704, 'close': 4710},
        {'open': 4710, 'high': 4715, 'low': 4708, 'close': 4713},
        {'open': 4713, 'high': 4718, 'low': 4711, 'close': 4716},
        {'open': 4716, 'high': 4722, 'low': 4714, 'close': 4720},
        {'open': 4720, 'high': 4725, 'low': 4718, 'close': 4723},
        {'open': 4723, 'high': 4728, 'low': 4721, 'close': 4726},
        {'open': 4726, 'high': 4730, 'low': 4724, 'close': 4728},
        {'open': 4728, 'high': 4732, 'low': 4726, 'close': 4730},
    ]


# ==============================================================
# Test 1: Uptrend + Twin Candle → BUY
# ==============================================================
def test_uptrend_twin_candle_buy(engine, mock_portfolio, mock_ohlc):
    """Test uptrend with twin candle → should BUY."""
    world_state = {
        'selected_tf': 'H1',
        'timeframe': 'H1',
        'chart_type': 'uptrend',
        'technique_candidate': 'twin_candle',
        'quality': 0.75,
        'range': {'high': 4750, 'low': 4600, 'usd': 150, 'pip': 15000},
        'current_price': 4715,
        'twin_candle': {
            'found': True,
            'candle1_idx': 48,
            'candle2_idx': 49,
            'technical_price': 4700.50,
            'body_pct': 0.08
        },
        'father_candle': {'found': False},
        'chart_detail': {
            'slope_angle': 46.5,
            'hh_hl': {'hh_count': 4, 'hl_count': 4, 'consecutive': True}
        },
        'swing_points': {
            'highs': [(10, 4720), (25, 4735), (45, 4748)],
            'lows': [(5, 4605), (20, 4650), (40, 4695)]
        },
        'ohlc_last_10': mock_ohlc
    }

    result = engine.decide(world_state, balance=300, portfolio_state=mock_portfolio)

    assert result['success']
    assert result['decision']['action'] == 'BUY'
    assert result['decision']['entry'] == 4700.50
    assert result['decision']['rr_ratio'] >= 1.0
    assert result['decision']['sl'] < result['decision']['entry']
    assert result['decision']['tp'] > result['decision']['entry']
    assert result['llm_log']['cost_usd'] == 0.0
    assert result['llm_log']['engine'] == 'python'
    assert result['llm_log']['latency_sec'] < 0.1


# ==============================================================
# Test 2: Downtrend + Twin Candle → SELL
# ==============================================================
def test_downtrend_twin_candle_sell(engine, mock_portfolio, mock_ohlc):
    """Test downtrend with twin candle → should SELL."""
    world_state = {
        'selected_tf': 'M15',
        'chart_type': 'downtrend',
        'technique_candidate': 'twin_candle',
        'quality': 0.70,
        'range': {'high': 4800, 'low': 4650, 'usd': 150, 'pip': 15000},
        'current_price': 4690,
        'twin_candle': {
            'found': True,
            'technical_price': 4705.00,
            'body_pct': 0.07
        },
        'father_candle': {'found': False},
        'chart_detail': {
            'slope_angle': 48.0,
            'lh_ll': {'lh_count': 4, 'll_count': 4, 'consecutive': True}
        },
        'swing_points': {
            'highs': [(10, 4790), (25, 4750), (40, 4710)],
            'lows': [(15, 4660), (30, 4655), (45, 4650)]
        },
        'ohlc_last_10': mock_ohlc
    }

    result = engine.decide(world_state, balance=300, portfolio_state=mock_portfolio)

    assert result['success']
    assert result['decision']['action'] == 'SELL'
    assert result['decision']['entry'] == 4705.00
    assert result['decision']['rr_ratio'] >= 1.0
    assert result['decision']['sl'] > result['decision']['entry']
    assert result['decision']['tp'] < result['decision']['entry']


# ==============================================================
# Test 3: Sideway Up at Top → SELL
# ==============================================================
def test_sideway_up_at_top_sell(engine, mock_portfolio, mock_ohlc):
    """Test sideway_up near top → should SELL."""
    world_state = {
        'selected_tf': 'M30',
        'chart_type': 'sideway_up',
        'technique_candidate': 'twin_candle',
        'quality': 0.68,
        'range': {'high': 4750, 'low': 4700, 'usd': 50, 'pip': 5000},
        'current_price': 4745,
        'twin_candle': {
            'found': True,
            'technical_price': 4745.00,
            'body_pct': 0.06
        },
        'father_candle': {'found': False},
        'chart_detail': {
            'box_high': 4750,
            'box_low': 4700,
            'box_pct': 0.25,
            'current_position': 'near_top'
        },
        'swing_points': {
            'highs': [(10, 4750), (25, 4748)],
            'lows': [(15, 4702), (30, 4701)]
        },
        'ohlc_last_10': mock_ohlc
    }

    result = engine.decide(world_state, balance=300, portfolio_state=mock_portfolio)

    assert result['success']
    assert result['decision']['action'] == 'SELL'


# ==============================================================
# Test 4: Sideway Up at Bottom → BUY
# ==============================================================
def test_sideway_up_at_bottom_buy(engine, mock_portfolio, mock_ohlc):
    """Test sideway_up near bottom → should BUY."""
    world_state = {
        'selected_tf': 'M30',
        'chart_type': 'sideway_up',
        'technique_candidate': 'twin_candle',
        'quality': 0.68,
        'range': {'high': 4750, 'low': 4700, 'usd': 50, 'pip': 5000},
        'current_price': 4705,
        'twin_candle': {
            'found': True,
            'technical_price': 4705.00,
            'body_pct': 0.06
        },
        'father_candle': {'found': False},
        'chart_detail': {
            'box_high': 4750,
            'box_low': 4700,
            'box_pct': 0.25,
            'current_position': 'near_bottom'
        },
        'swing_points': {
            'highs': [(10, 4750), (25, 4748)],
            'lows': [(15, 4702), (30, 4701)]
        },
        'ohlc_last_10': mock_ohlc
    }

    result = engine.decide(world_state, balance=300, portfolio_state=mock_portfolio)

    assert result['success']
    assert result['decision']['action'] == 'BUY'


# ==============================================================
# Test 5: Sideway Middle → SKIP
# ==============================================================
def test_sideway_middle_skip(engine, mock_portfolio, mock_ohlc):
    """Test sideway price in middle → should SKIP."""
    world_state = {
        'selected_tf': 'M30',
        'chart_type': 'sideway_up',
        'technique_candidate': 'twin_candle',
        'quality': 0.68,
        'range': {'high': 4750, 'low': 4700, 'usd': 50, 'pip': 5000},
        'current_price': 4725,
        'twin_candle': {
            'found': True,
            'technical_price': 4725.00,
            'body_pct': 0.06
        },
        'father_candle': {'found': False},
        'chart_detail': {
            'box_high': 4750,
            'box_low': 4700,
            'box_pct': 0.25,
            'current_position': 'middle'
        },
        'swing_points': {'highs': [], 'lows': []},
        'ohlc_last_10': mock_ohlc
    }

    result = engine.decide(world_state, balance=300, portfolio_state=mock_portfolio)

    assert result['success']
    assert result['decision']['action'] == 'SKIP'
    assert 'middle' in result['decision']['skip_reason'].lower()


# ==============================================================
# Test 6: Mai Ruay - Father Down → BUY
# ==============================================================
def test_mai_ruay_father_down_buy(engine, mock_portfolio, mock_ohlc):
    """Test mai_ruay with father down → should BUY."""
    world_state = {
        'selected_tf': 'M15',
        'chart_type': 'unclear',
        'technique_candidate': 'mai_ruay',
        'quality': 0.70,
        'range': {'high': 4750, 'low': 4600, 'usd': 150, 'pip': 15000},
        'current_price': 4650,
        'twin_candle': {'found': False},
        'father_candle': {
            'found': True,
            'is_valid': True,
            'direction': 'down',
            'quality': 0.85,
            'candle_count': 3,
            'pct_range': 0.80,
            'mother_candle': {
                'found': True,
                'valid': True,
                'body_ratio': 0.15,
                'beauty': 'excellent',
                'reversed_close': True,
                'technical_price': 4655.00
            }
        },
        'chart_detail': {},
        'swing_points': {
            'highs': [(5, 4740), (20, 4720)],
            'lows': [(25, 4645)]
        },
        'ohlc_last_10': mock_ohlc[:6] + [
            {'open': 4720, 'high': 4722, 'low': 4680, 'close': 4685},  # Father candle 1
            {'open': 4685, 'high': 4690, 'low': 4655, 'close': 4660},  # Father candle 2
            {'open': 4660, 'high': 4665, 'low': 4645, 'close': 4650},  # Father candle 3
            {'open': 4650, 'high': 4658, 'low': 4648, 'close': 4656},  # Mother candle (most recent)
        ]
    }

    result = engine.decide(world_state, balance=300, portfolio_state=mock_portfolio)

    assert result['success']
    assert result['decision']['action'] == 'BUY'
    assert result['decision']['technique'] == 'mai_ruay'
    assert result['decision']['entry'] == 4655.00
    assert result['decision']['rr_ratio'] >= 1.0


# ==============================================================
# Test 7: Mai Ruay - Father Up → SELL
# ==============================================================
def test_mai_ruay_father_up_sell(engine, mock_portfolio, mock_ohlc):
    """Test mai_ruay with father up → should SELL."""
    world_state = {
        'selected_tf': 'M15',
        'chart_type': 'unclear',
        'technique_candidate': 'mai_ruay',
        'quality': 0.70,
        'range': {'high': 4750, 'low': 4600, 'usd': 150, 'pip': 15000},
        'current_price': 4735,
        'twin_candle': {'found': False},
        'father_candle': {
            'found': True,
            'is_valid': True,
            'direction': 'up',
            'quality': 0.85,
            'candle_count': 3,
            'pct_range': 0.80,
            'mother_candle': {
                'found': True,
                'valid': True,
                'body_ratio': 0.15,
                'beauty': 'excellent',
                'reversed_close': True,
                'technical_price': 4730.00
            }
        },
        'chart_detail': {},
        'swing_points': {
            'highs': [(25, 4745)],
            'lows': [(5, 4650), (20, 4670)]
        },
        'ohlc_last_10': mock_ohlc[:6] + [
            {'open': 4650, 'high': 4665, 'low': 4648, 'close': 4660},  # Father candle 1
            {'open': 4660, 'high': 4700, 'low': 4658, 'close': 4695},  # Father candle 2
            {'open': 4695, 'high': 4745, 'low': 4693, 'close': 4740},  # Father candle 3
            {'open': 4740, 'high': 4742, 'low': 4728, 'close': 4730},  # Mother candle (most recent)
        ]
    }

    result = engine.decide(world_state, balance=300, portfolio_state=mock_portfolio)

    assert result['success']
    assert result['decision']['action'] == 'SELL'
    assert result['decision']['technique'] == 'mai_ruay'


# ==============================================================
# Test 8: Mai Ruay Against Trend → SKIP
# ==============================================================
def test_mai_ruay_against_trend_skip(engine, mock_portfolio, mock_ohlc):
    """Test mai_ruay SELL against uptrend → should SKIP."""
    world_state = {
        'selected_tf': 'H1',
        'chart_type': 'uptrend',
        'technique_candidate': 'mai_ruay',
        'quality': 0.70,
        'range': {'high': 4750, 'low': 4600, 'usd': 150, 'pip': 15000},
        'current_price': 4700,
        'twin_candle': {'found': False},
        'father_candle': {
            'found': True,
            'is_valid': True,
            'direction': 'up',  # Would trigger SELL
            'quality': 0.85,
            'candle_count': 3,
            'mother_candle': {
                'valid': True,
                'technical_price': 4700.00,
                'body_ratio': 0.15
            }
        },
        'chart_detail': {},
        'swing_points': {'highs': [], 'lows': []},
        'ohlc_last_10': mock_ohlc
    }

    result = engine.decide(world_state, balance=300, portfolio_state=mock_portfolio)

    assert result['success']
    assert result['decision']['action'] == 'SKIP'
    assert 'against' in result['decision']['skip_reason'].lower()


# ==============================================================
# Test 9: Mai Ruay Mother Too Big → SKIP
# ==============================================================
def test_mai_ruay_mother_too_big_skip(engine, mock_portfolio, mock_ohlc):
    """Test mai_ruay with mother body > 30% → should SKIP."""
    world_state = {
        'selected_tf': 'M15',
        'chart_type': 'unclear',
        'technique_candidate': 'mai_ruay',
        'quality': 0.70,
        'range': {'high': 4750, 'low': 4600, 'usd': 150, 'pip': 15000},
        'current_price': 4650,
        'twin_candle': {'found': False},
        'father_candle': {
            'found': True,
            'is_valid': True,
            'direction': 'down',
            'quality': 0.85,
            'candle_count': 3,
            'mother_candle': {
                'valid': True,
                'body_ratio': 0.35,  # Too big!
                'technical_price': 4655.00
            }
        },
        'chart_detail': {},
        'swing_points': {'highs': [], 'lows': []},
        'ohlc_last_10': mock_ohlc
    }

    result = engine.decide(world_state, balance=300, portfolio_state=mock_portfolio)

    assert result['success']
    assert result['decision']['action'] == 'SKIP'
    assert 'big' in result['decision']['skip_reason'].lower()


# ==============================================================
# Test 10: Breakout Follow - Uptrend → BUY
# ==============================================================
def test_breakout_up_with_uptrend_buy(engine, mock_portfolio, mock_ohlc):
    """Test breakout up with uptrend → should BUY."""
    world_state = {
        'selected_tf': 'M30',
        'chart_type': 'uptrend',
        'technique_candidate': 'breakout_follow',
        'quality': 0.72,
        'range': {'high': 4750, 'low': 4600, 'usd': 150, 'pip': 15000},
        'current_price': 4720,
        'twin_candle': {'found': False},
        'father_candle': {'found': False},
        'chart_detail': {
            'breakout_box': {
                'found': True,
                'box_high': 4715,
                'box_low': 4700,
                'box_pct': 0.10,
                'breakout_direction': 'up'
            }
        },
        'swing_points': {
            'highs': [(30, 4740)],
            'lows': [(10, 4695)]
        },
        'ohlc_last_10': mock_ohlc
    }

    result = engine.decide(world_state, balance=300, portfolio_state=mock_portfolio)

    assert result['success']
    assert result['decision']['action'] == 'BUY'
    assert result['decision']['technique'] == 'breakout_follow'


# ==============================================================
# Test 11: Breakout Down Against Uptrend → SKIP
# ==============================================================
def test_breakout_down_with_uptrend_skip(engine, mock_portfolio, mock_ohlc):
    """Test breakout down with uptrend → should SKIP."""
    world_state = {
        'selected_tf': 'M30',
        'chart_type': 'uptrend',
        'technique_candidate': 'breakout_follow',
        'quality': 0.72,
        'range': {'high': 4750, 'low': 4600, 'usd': 150, 'pip': 15000},
        'current_price': 4695,
        'twin_candle': {'found': False},
        'father_candle': {'found': False},
        'chart_detail': {
            'breakout_box': {
                'found': True,
                'box_high': 4715,
                'box_low': 4700,
                'box_pct': 0.10,
                'breakout_direction': 'down'
            }
        },
        'swing_points': {'highs': [], 'lows': []},
        'ohlc_last_10': mock_ohlc
    }

    result = engine.decide(world_state, balance=300, portfolio_state=mock_portfolio)

    assert result['success']
    assert result['decision']['action'] == 'SKIP'


# ==============================================================
# Test 12: Mountain at Base → BUY
# ==============================================================
def test_mountain_at_base_buy(engine, mock_portfolio, mock_ohlc):
    """Test mountain at right base → should BUY."""
    world_state = {
        'selected_tf': 'H4',
        'chart_type': 'mountain',
        'technique_candidate': 'twin_candle',
        'quality': 0.72,
        'range': {'high': 4800, 'low': 4600, 'usd': 200, 'pip': 20000},
        'current_price': 4620,
        'twin_candle': {
            'found': True,
            'technical_price': 4615.00,
            'body_pct': 0.08
        },
        'father_candle': {'found': False},
        'chart_detail': {
            'peak_price': 4790,
            'left_base_price': 4610,
            'right_base_price': 4620,
            'height_pct': 0.90,
            'tolerance_ok': True,
            'twin_candle_base': {'found': True, 'technical_price': 4615.00}
        },
        'swing_points': {
            'highs': [(30, 4790)],
            'lows': [(10, 4610)]
        },
        'ohlc_last_10': mock_ohlc
    }

    result = engine.decide(world_state, balance=300, portfolio_state=mock_portfolio)

    assert result['success']
    assert result['decision']['action'] == 'BUY'
    assert result['decision']['chart_type'] == 'mountain'


# ==============================================================
# Test 13: Mountain Not at Base → SKIP
# ==============================================================
def test_mountain_not_at_base_skip(engine, mock_portfolio, mock_ohlc):
    """Test mountain not at right base yet → should SKIP."""
    world_state = {
        'selected_tf': 'H4',
        'chart_type': 'mountain',
        'technique_candidate': 'twin_candle',
        'quality': 0.72,
        'range': {'high': 4800, 'low': 4600, 'usd': 200, 'pip': 20000},
        'current_price': 4650,
        'twin_candle': {'found': False},
        'father_candle': {'found': False},
        'chart_detail': {
            'peak_price': 4790,
            'left_base_price': 4610,
            'right_base_price': 4650,
            'height_pct': 0.90,
            'tolerance_ok': False  # Not at base yet
        },
        'swing_points': {'highs': [], 'lows': []},
        'ohlc_last_10': mock_ohlc
    }

    result = engine.decide(world_state, balance=300, portfolio_state=mock_portfolio)

    assert result['success']
    assert result['decision']['action'] == 'SKIP'
    assert 'base' in result['decision']['skip_reason'].lower()


# ==============================================================
# Test 14: Determinism - Same Input = Same Output
# ==============================================================
def test_deterministic(engine, mock_portfolio, mock_ohlc):
    """Test that Python engine is deterministic."""
    world_state = {
        'selected_tf': 'H1',
        'chart_type': 'uptrend',
        'technique_candidate': 'twin_candle',
        'quality': 0.75,
        'range': {'high': 4750, 'low': 4600, 'usd': 150, 'pip': 15000},
        'current_price': 4715,
        'twin_candle': {
            'found': True,
            'technical_price': 4700.50,
            'body_pct': 0.08
        },
        'father_candle': {'found': False},
        'chart_detail': {},
        'swing_points': {
            'highs': [(10, 4720), (25, 4735)],
            'lows': [(5, 4605), (20, 4650)]
        },
        'ohlc_last_10': mock_ohlc
    }

    result1 = engine.decide(world_state, balance=300, portfolio_state=mock_portfolio)
    result2 = engine.decide(world_state, balance=300, portfolio_state=mock_portfolio)

    # Compare key fields (excluding timestamp)
    assert result1['decision']['action'] == result2['decision']['action']
    if result1['decision']['action'] != 'SKIP':
        assert result1['decision']['entry'] == result2['decision']['entry']
        assert result1['decision']['sl'] == result2['decision']['sl']
        assert result1['decision']['tp'] == result2['decision']['tp']
        assert result1['decision']['rr_ratio'] == result2['decision']['rr_ratio']


# ==============================================================
# Test 15: Performance - <50ms per decision
# ==============================================================
def test_performance(engine, mock_portfolio, mock_ohlc):
    """Test that decisions are fast (<50ms)."""
    import time

    world_state = {
        'selected_tf': 'H1',
        'chart_type': 'uptrend',
        'technique_candidate': 'twin_candle',
        'quality': 0.75,
        'range': {'high': 4750, 'low': 4600, 'usd': 150, 'pip': 15000},
        'current_price': 4715,
        'twin_candle': {
            'found': True,
            'technical_price': 4700.50,
            'body_pct': 0.08
        },
        'father_candle': {'found': False},
        'chart_detail': {},
        'swing_points': {
            'highs': [(10, 4720)],
            'lows': [(5, 4605)]
        },
        'ohlc_last_10': mock_ohlc
    }

    start = time.time()
    for _ in range(100):
        engine.decide(world_state, balance=300, portfolio_state=mock_portfolio)
    elapsed = (time.time() - start) / 100

    assert elapsed < 0.05, f"Too slow: {elapsed*1000:.1f}ms per decision"


# ==============================================================
# Test 16: Output Schema Validation
# ==============================================================
def test_output_schema(engine, mock_portfolio, mock_ohlc):
    """Test that output has all required keys."""
    world_state = {
        'selected_tf': 'H1',
        'chart_type': 'uptrend',
        'technique_candidate': 'twin_candle',
        'quality': 0.75,
        'range': {'high': 4750, 'low': 4600, 'usd': 150, 'pip': 15000},
        'current_price': 4715,
        'twin_candle': {
            'found': True,
            'technical_price': 4700.50,
            'body_pct': 0.08
        },
        'father_candle': {'found': False},
        'chart_detail': {},
        'swing_points': {
            'highs': [(10, 4720)],
            'lows': [(5, 4605)]
        },
        'ohlc_last_10': mock_ohlc
    }

    result = engine.decide(world_state, balance=300, portfolio_state=mock_portfolio)

    # Top-level keys
    assert set(result.keys()) >= {'decision', 'llm_log', 'validation', 'success'}

    # Decision keys (for non-SKIP)
    if result['decision']['action'] != 'SKIP':
        required = {
            'chart_type', 'technique', 'action', 'confidence',
            'entry', 'sl', 'tp', 'rr_ratio', 'sl_pip', 'tp_pip', 'reason'
        }
        assert set(result['decision'].keys()) >= required

        # Type checks
        assert isinstance(result['decision']['entry'], float)
        assert isinstance(result['decision']['sl'], float)
        assert isinstance(result['decision']['tp'], float)
        assert isinstance(result['decision']['rr_ratio'], float)
        assert isinstance(result['decision']['sl_pip'], int)
        assert isinstance(result['decision']['tp_pip'], int)

    # LLM log structure
    log_required = {
        'timestamp', 'model', 'total_tokens', 'cost_usd',
        'latency_sec', 'action', 'engine'
    }
    assert set(result['llm_log'].keys()) >= log_required
    assert result['llm_log']['cost_usd'] == 0.0
    assert result['llm_log']['engine'] == 'python'
    assert result['llm_log']['model'] == 'python_rules'


# ==============================================================
# Test 17: No Twin Candle → SKIP
# ==============================================================
def test_no_twin_candle_skip(engine, mock_portfolio, mock_ohlc):
    """Test twin_candle technique but twin not found → SKIP."""
    world_state = {
        'selected_tf': 'H1',
        'chart_type': 'uptrend',
        'technique_candidate': 'twin_candle',
        'quality': 0.75,
        'range': {'high': 4750, 'low': 4600, 'usd': 150, 'pip': 15000},
        'current_price': 4715,
        'twin_candle': {'found': False},  # Not found!
        'father_candle': {'found': False},
        'chart_detail': {},
        'swing_points': {'highs': [], 'lows': []},
        'ohlc_last_10': mock_ohlc
    }

    result = engine.decide(world_state, balance=300, portfolio_state=mock_portfolio)

    assert result['success']
    assert result['decision']['action'] == 'SKIP'
    assert 'twin' in result['decision']['skip_reason'].lower()


# ==============================================================
# Test 18: Technique = skip → SKIP
# ==============================================================
def test_technique_skip(engine, mock_portfolio, mock_ohlc):
    """Test when G1 says technique='skip' → SKIP."""
    world_state = {
        'selected_tf': 'H1',
        'chart_type': 'unclear',
        'technique_candidate': 'skip',  # G1 found no setup
        'quality': 0.50,
        'range': {'high': 4750, 'low': 4600, 'usd': 150, 'pip': 15000},
        'current_price': 4715,
        'twin_candle': {'found': False},
        'father_candle': {'found': False},
        'chart_detail': {},
        'swing_points': {'highs': [], 'lows': []},
        'ohlc_last_10': mock_ohlc
    }

    result = engine.decide(world_state, balance=300, portfolio_state=mock_portfolio)

    assert result['success']
    assert result['decision']['action'] == 'SKIP'
