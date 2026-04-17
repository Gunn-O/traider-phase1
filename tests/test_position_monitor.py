"""
Test G4c Position Monitor

pytest tests/test_position_monitor.py
"""

import pytest
from agents.g4_position_monitor import (
    check_positions_on_candle_close,
    check_trailing_sl,
    calc_pnl,
    generate_trade_id,
    generate_plan_id
)


def test_calc_pnl_buy():
    """Test P&L calculation for BUY"""
    pnl = calc_pnl('BUY', entry=3050.0, close=3060.0, lot=0.01)
    # (3060 - 3050) × 0.01 × 100 = 10.0
    assert pnl == 10.0


def test_calc_pnl_sell():
    """Test P&L calculation for SELL"""
    pnl = calc_pnl('SELL', entry=3050.0, close=3040.0, lot=0.01)
    # (3050 - 3040) × 0.01 × 100 = 10.0
    assert pnl == 10.0


def test_calc_pnl_loss():
    """Test P&L calculation for LOSS"""
    pnl = calc_pnl('BUY', entry=3050.0, close=3040.0, lot=0.01)
    # (3040 - 3050) × 0.01 × 100 = -10.0
    assert pnl == -10.0


def test_sl_hit_buy():
    """Test SL hit detection for BUY"""
    candle = {
        'timestamp': '2026-04-08T10:00:00',
        'open': 3050.0,
        'high': 3055.0,
        'low': 3040.0,  # Hit SL
        'close': 3052.0
    }
    orders = [{
        'trade_id': 'TRD-001',
        'action': 'BUY',
        'entry_price': 3050.0,
        'sl_price': 3041.0,
        'tp_price': 3080.0,
        'lot_size': 0.01,
        'result': 'PENDING'
    }]

    updates = check_positions_on_candle_close(candle, orders)
    assert len(updates) == 1
    assert updates[0]['type'] == 'close'
    assert updates[0]['result'] == 'LOSS'
    assert updates[0]['close_reason'] == 'SL_HIT'


def test_tp_hit_buy():
    """Test TP hit detection for BUY"""
    candle = {
        'timestamp': '2026-04-08T10:00:00',
        'open': 3075.0,
        'high': 3085.0,  # Hit TP
        'low': 3070.0,
        'close': 3082.0
    }
    orders = [{
        'trade_id': 'TRD-001',
        'action': 'BUY',
        'entry_price': 3050.0,
        'sl_price': 3041.0,
        'tp_price': 3080.0,
        'lot_size': 0.01,
        'result': 'PENDING'
    }]

    updates = check_positions_on_candle_close(candle, orders)
    assert len(updates) == 1
    assert updates[0]['type'] == 'close'
    assert updates[0]['result'] == 'WIN'
    assert updates[0]['close_reason'] == 'TP_HIT'


def test_both_hit_conservative():
    """Test conservative rule — ถ้า hit ทั้ง SL และ TP → SL ก่อน"""
    candle = {
        'timestamp': '2026-04-08T10:00:00',
        'open': 3050.0,
        'high': 3085.0,  # Hit TP
        'low': 3040.0,   # Hit SL
        'close': 3082.0
    }
    orders = [{
        'trade_id': 'TRD-001',
        'action': 'BUY',
        'entry_price': 3050.0,
        'sl_price': 3041.0,
        'tp_price': 3080.0,
        'lot_size': 0.01,
        'result': 'PENDING'
    }]

    updates = check_positions_on_candle_close(candle, orders)
    assert updates[0]['result'] == 'LOSS'
    assert updates[0]['close_reason'] == 'SL_HIT'


def test_generate_trade_id_unique():
    """Test trade ID generation — ต้องไม่ซ้ำ"""
    id1 = generate_trade_id('PLAN-001', 1)
    id2 = generate_trade_id('PLAN-001', 2)
    assert id1 != id2
    assert id1.startswith('TRD-')
    assert id2.startswith('TRD-')


def test_generate_plan_id_unique():
    """Test plan ID generation — ต้องไม่ซ้ำ"""
    plan1 = generate_plan_id()
    plan2 = generate_plan_id()
    assert plan1 != plan2
    assert plan1.startswith('PLAN-')
