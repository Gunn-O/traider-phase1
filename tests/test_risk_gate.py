"""
Test G3c Risk Gate

pytest tests/test_risk_gate.py
"""

import pytest
from agents.g3_risk_gate import guardian_check, reset_consecutive_loss, increment_consecutive_loss


def test_guardian_normal_case():
    """Test normal case — should approve"""
    decision = {
        'action': 'BUY',
        'entry': 3050.0,
        'sl': 3041.0,
        'tp': 3080.0,
        'rr_ratio': 3.33
    }
    lot_info = {'lot_total': 0.03, 'suggested_orders': 3}
    portfolio = {
        'active_plan_id': 'ไม่มีแผนที่เปิดอยู่',
        'consecutive_loss': 0,
        'total_loss_pct': 0.0,
        'news_flag': False
    }

    result = guardian_check(decision, lot_info, portfolio)
    assert result['approved'] == True
    assert result['blocked_by'] == ''


def test_guardian_block_active_plan():
    """Test block เมื่อมี active plan"""
    decision = {'action': 'BUY', 'rr_ratio': 2.0}
    lot_info = {'lot_total': 0.03}
    portfolio = {
        'active_plan_id': 'PLAN-20260408-001',
        'consecutive_loss': 0,
        'total_loss_pct': 0.0
    }

    result = guardian_check(decision, lot_info, portfolio)
    assert result['approved'] == False
    assert result['blocked_by'] == 'active_plan'


def test_guardian_block_consecutive_loss():
    """Test block เมื่อ consecutive loss >= 3"""
    decision = {'action': 'BUY', 'rr_ratio': 2.0}
    lot_info = {'lot_total': 0.03}
    portfolio = {
        'active_plan_id': 'ไม่มีแผนที่เปิดอยู่',
        'consecutive_loss': 3,
        'total_loss_pct': 0.0
    }

    result = guardian_check(decision, lot_info, portfolio)
    assert result['approved'] == False
    assert result['blocked_by'] == 'consecutive_loss'


def test_guardian_block_rr_ratio():
    """Test block เมื่อ R:R < 1.0"""
    decision = {'action': 'BUY', 'rr_ratio': 0.8}
    lot_info = {'lot_total': 0.03}
    portfolio = {
        'active_plan_id': 'ไม่มีแผนที่เปิดอยู่',
        'consecutive_loss': 0,
        'total_loss_pct': 0.0
    }

    result = guardian_check(decision, lot_info, portfolio)
    assert result['approved'] == False
    assert result['blocked_by'] == 'rr_ratio'


def test_consecutive_loss_increment():
    """Test increment consecutive loss"""
    portfolio = {'consecutive_loss': 0}
    portfolio = increment_consecutive_loss(portfolio)
    assert portfolio['consecutive_loss'] == 1

    portfolio = increment_consecutive_loss(portfolio)
    assert portfolio['consecutive_loss'] == 2


def test_consecutive_loss_reset():
    """Test reset consecutive loss"""
    portfolio = {'consecutive_loss': 5}
    portfolio = reset_consecutive_loss(portfolio)
    assert portfolio['consecutive_loss'] == 0
