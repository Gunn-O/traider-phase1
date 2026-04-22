"""
Unit Tests for PaperBroker

Tests:
- open_position and get_open_positions
- update_positions → SL hit
- update_positions → TP hit
- close_all (emergency stop)
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch
from agents.paper_broker import PaperBroker, PAPER_TICKET_START


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_mt5():
    """Mock MetaTrader5 module"""
    with patch('agents.paper_broker.mt5') as mock_mt5_module, \
         patch('agents.paper_broker.MT5_AVAILABLE', True):
        # Mock tick data
        mock_tick = Mock()
        mock_tick.bid = 3245.50
        mock_tick.ask = 3245.60
        mock_mt5_module.symbol_info_tick.return_value = mock_tick
        yield mock_mt5_module


@pytest.fixture
def broker(mock_mt5):
    """Create PaperBroker instance with mocked MT5"""
    return PaperBroker(symbol="XAUUSDm")


@pytest.fixture
def candle_time():
    """Sample candle timestamp"""
    return datetime(2026, 4, 18, 10, 30, 0)


# ============================================================================
# TEST OPEN POSITION
# ============================================================================

def test_open_position_buy(broker, candle_time):
    """Test opening BUY position"""
    ticket = broker.open_position(
        action="BUY",
        lot=0.01,
        sl=3230.00,
        tp=3275.00,
        plan_id="PLAN-001",
        candle_time=candle_time
    )

    # Check ticket number
    assert ticket == PAPER_TICKET_START + 1
    assert ticket >= 90000

    # Check position in broker
    positions = broker.get_open_positions()
    assert len(positions) == 1

    pos = positions[0]
    assert pos["ticket"] == ticket
    assert pos["action"] == "BUY"
    assert pos["lot"] == 0.01
    assert pos["entry"] == 3245.60  # ask price
    assert pos["sl"] == 3230.00
    assert pos["tp"] == 3275.00
    assert pos["plan_id"] == "PLAN-001"
    assert pos["result"] == "PENDING"
    assert pos["pnl"] == 0.0


def test_open_position_sell(broker, candle_time):
    """Test opening SELL position"""
    ticket = broker.open_position(
        action="SELL",
        lot=0.01,
        sl=3260.00,
        tp=3200.00,
        plan_id="PLAN-002",
        candle_time=candle_time
    )

    positions = broker.get_open_positions()
    assert len(positions) == 1

    pos = positions[0]
    assert pos["action"] == "SELL"
    assert pos["entry"] == 3245.50  # bid price
    assert pos["sl"] == 3260.00
    assert pos["tp"] == 3200.00


def test_open_multiple_positions(broker, candle_time):
    """Test opening multiple positions"""
    ticket1 = broker.open_position("BUY", 0.01, 3230, 3275, "PLAN-001", candle_time)
    ticket2 = broker.open_position("SELL", 0.01, 3260, 3200, "PLAN-002", candle_time)

    positions = broker.get_open_positions()
    assert len(positions) == 2
    assert ticket2 == ticket1 + 1  # Sequential tickets


# ============================================================================
# TEST SL HIT
# ============================================================================

def test_update_positions_sl_hit_buy(broker, mock_mt5, candle_time):
    """Test BUY position hits SL"""
    # Open BUY @ 3245.60, SL @ 3230
    broker.open_position("BUY", 0.01, 3230.00, 3275.00, "PLAN-001", candle_time)

    # Price drops to 3230 (SL hit)
    mock_tick = Mock()
    mock_tick.bid = 3230.00
    mock_tick.ask = 3230.10
    mock_mt5.symbol_info_tick.return_value = mock_tick

    newly_closed = broker.update_positions(candle_time)

    # Should close position
    assert len(newly_closed) == 1
    closed = newly_closed[0]

    assert closed["result"] == "LOSS"
    assert closed["close_reason"] == "SL_HIT"
    assert closed["close_price"] == 3230.00

    # Calculate P&L: (3230 - 3245.60) * 0.01 * 100 = -15.60
    expected_pnl = (3230.00 - 3245.60) * 0.01 * 100
    assert abs(closed["pnl"] - expected_pnl) < 0.01

    # No more open positions
    assert len(broker.get_open_positions()) == 0

    # Should be in closed_trades
    assert len(broker.get_closed_trades()) == 1


def test_update_positions_sl_hit_sell(broker, mock_mt5, candle_time):
    """Test SELL position hits SL"""
    # Open SELL @ 3245.50, SL @ 3260
    broker.open_position("SELL", 0.01, 3260.00, 3200.00, "PLAN-001", candle_time)

    # Price rises to 3260 (SL hit)
    mock_tick = Mock()
    mock_tick.bid = 3259.90
    mock_tick.ask = 3260.00
    mock_mt5.symbol_info_tick.return_value = mock_tick

    newly_closed = broker.update_positions(candle_time)

    assert len(newly_closed) == 1
    closed = newly_closed[0]

    assert closed["result"] == "LOSS"
    assert closed["close_reason"] == "SL_HIT"
    assert closed["close_price"] == 3260.00

    # Calculate P&L: (3245.50 - 3260) * 0.01 * 100 = -14.50
    expected_pnl = (3245.50 - 3260.00) * 0.01 * 100
    assert abs(closed["pnl"] - expected_pnl) < 0.01


# ============================================================================
# TEST TP HIT
# ============================================================================

def test_update_positions_tp_hit_buy(broker, mock_mt5, candle_time):
    """Test BUY position hits TP"""
    # Open BUY @ 3245.60, TP @ 3275
    broker.open_position("BUY", 0.01, 3230.00, 3275.00, "PLAN-001", candle_time)

    # Price rises to 3275 (TP hit)
    mock_tick = Mock()
    mock_tick.bid = 3275.00
    mock_tick.ask = 3275.10
    mock_mt5.symbol_info_tick.return_value = mock_tick

    newly_closed = broker.update_positions(candle_time)

    assert len(newly_closed) == 1
    closed = newly_closed[0]

    assert closed["result"] == "WIN"
    assert closed["close_reason"] == "TP_HIT"
    assert closed["close_price"] == 3275.00

    # Calculate P&L: (3275 - 3245.60) * 0.01 * 100 = +29.40
    expected_pnl = (3275.00 - 3245.60) * 0.01 * 100
    assert abs(closed["pnl"] - expected_pnl) < 0.01


def test_update_positions_tp_hit_sell(broker, mock_mt5, candle_time):
    """Test SELL position hits TP"""
    # Open SELL @ 3245.50, TP @ 3200
    broker.open_position("SELL", 0.01, 3260.00, 3200.00, "PLAN-001", candle_time)

    # Price drops to 3200 (TP hit) - ASK must be <= TP for SELL
    mock_tick = Mock()
    mock_tick.bid = 3199.90
    mock_tick.ask = 3200.00  # ASK at TP triggers close
    mock_mt5.symbol_info_tick.return_value = mock_tick

    newly_closed = broker.update_positions(candle_time)

    assert len(newly_closed) == 1
    closed = newly_closed[0]

    assert closed["result"] == "WIN"
    assert closed["close_reason"] == "TP_HIT"
    assert closed["close_price"] == 3200.00

    # Calculate P&L: (3245.50 - 3200) * 0.01 * 100 = +45.50
    expected_pnl = (3245.50 - 3200.00) * 0.01 * 100
    assert abs(closed["pnl"] - expected_pnl) < 0.01


# ============================================================================
# TEST NO CLOSE
# ============================================================================

def test_update_positions_no_close(broker, mock_mt5, candle_time):
    """Test update when price hasn't hit SL/TP"""
    # Open BUY @ 3245.60, SL @ 3230, TP @ 3275
    broker.open_position("BUY", 0.01, 3230.00, 3275.00, "PLAN-001", candle_time)

    # Price at 3250 (between SL and TP)
    mock_tick = Mock()
    mock_tick.bid = 3250.00
    mock_tick.ask = 3250.10
    mock_mt5.symbol_info_tick.return_value = mock_tick

    newly_closed = broker.update_positions(candle_time)

    # Should not close
    assert len(newly_closed) == 0
    assert len(broker.get_open_positions()) == 1

    # P&L should be updated
    pos = broker.get_open_positions()[0]
    expected_pnl = (3250.00 - 3245.60) * 0.01 * 100
    assert abs(pos["pnl"] - expected_pnl) < 0.01


# ============================================================================
# TEST CLOSE ALL
# ============================================================================

def test_close_all(broker, mock_mt5, candle_time):
    """Test emergency close all positions"""
    # Open 2 positions
    broker.open_position("BUY", 0.01, 3230, 3275, "PLAN-001", candle_time)
    broker.open_position("SELL", 0.01, 3260, 3200, "PLAN-002", candle_time)

    assert len(broker.get_open_positions()) == 2

    # Close all at current price
    mock_tick = Mock()
    mock_tick.bid = 3250.00
    mock_tick.ask = 3250.10
    mock_mt5.symbol_info_tick.return_value = mock_tick

    closed = broker.close_all(candle_time)

    # Should close both
    assert len(closed) == 2
    assert len(broker.get_open_positions()) == 0
    assert len(broker.get_closed_trades()) == 2

    # Check close reasons
    for pos in closed:
        assert pos["close_reason"] == "MANUAL"


# ============================================================================
# TEST STATISTICS
# ============================================================================

def test_get_stats(broker, mock_mt5, candle_time):
    """Test get_stats() method"""
    # Open and close some positions
    broker.open_position("BUY", 0.01, 3230, 3275, "PLAN-001", candle_time)

    # TP hit (WIN)
    mock_tick = Mock()
    mock_tick.bid = 3275.00
    mock_tick.ask = 3275.10
    mock_mt5.symbol_info_tick.return_value = mock_tick
    broker.update_positions(candle_time)

    # Reset price before opening SELL
    mock_tick2 = Mock()
    mock_tick2.bid = 3245.50
    mock_tick2.ask = 3245.60
    mock_mt5.symbol_info_tick.return_value = mock_tick2

    # Open SELL and hit SL (LOSS) - ASK must be >= SL for SELL
    broker.open_position("SELL", 0.01, 3260, 3200, "PLAN-002", candle_time)

    # Price moves up to SL
    mock_tick3 = Mock()
    mock_tick3.bid = 3260.10
    mock_tick3.ask = 3260.10  # ASK >= SL triggers stop loss
    mock_mt5.symbol_info_tick.return_value = mock_tick3
    broker.update_positions(candle_time)

    stats = broker.get_stats()
    assert stats["total_trades"] == 2
    assert stats["wins"] == 1
    assert stats["losses"] == 1
    assert stats["win_rate"] == 0.5
    assert "total_pnl" in stats


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
