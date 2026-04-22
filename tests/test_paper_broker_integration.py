"""
Integration Test for PaperBroker + main.py

Tests:
- create_broker() factory function
- Broker initialization in TraiderMainLoop
- Order execution via broker
- Position monitoring with broker sync
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_env():
    """Mock environment variables"""
    with patch.dict('os.environ', {
        'ACCOUNT_BALANCE': '500',
        'ANTHROPIC_API_KEY': 'sk-ant-test',
        'DATA_MODE': 'simulate',
        'SHEETS_ENABLED': 'false',
        'LINE_NOTIFY_ENABLED': 'false'
    }):
        yield


@pytest.fixture
def mock_bot_state():
    """Mock bot_state"""
    with patch('main.bot_state', {
        'status': 'stopped',
        'mode': 'paper',
        'symbol': 'XAUUSDm',
        'trading_tf': 'M5'
    }):
        yield


@pytest.fixture
def mock_mt5():
    """Mock MetaTrader5 for PaperBroker"""
    with patch('agents.paper_broker.mt5') as mock_mt5_module, \
         patch('agents.paper_broker.MT5_AVAILABLE', True):
        # Mock tick data
        mock_tick = Mock()
        mock_tick.bid = 3245.50
        mock_tick.ask = 3245.60
        mock_mt5_module.symbol_info_tick.return_value = mock_tick
        yield mock_mt5_module


# ============================================================================
# TEST FACTORY FUNCTION
# ============================================================================

def test_create_broker_paper_mode(mock_mt5):
    """Test create_broker() returns PaperBroker for paper mode"""
    from main import create_broker

    broker = create_broker('paper', 'XAUUSDm')

    assert broker is not None
    assert broker.__class__.__name__ == 'PaperBroker'
    assert broker.symbol == 'XAUUSDm'


def test_create_broker_micro_mode():
    """Test create_broker() returns None for micro mode"""
    from main import create_broker

    broker = create_broker('micro', 'XAUUSDm')

    assert broker is None


def test_create_broker_live_mode():
    """Test create_broker() returns None for live mode"""
    from main import create_broker

    broker = create_broker('live', 'XAUUSD')

    assert broker is None


# ============================================================================
# TEST TRAIDER INITIALIZATION
# ============================================================================

@patch('agents.g4_reflector.Reflector')
@patch('agents.g3_python_decision.G3PythonDecision')
@patch('agents.g2_prefilter.G2Prefilter')
@patch('agents.g1_pattern_detector.G1PatternDetector')
@patch('agents.g4_sheets_logger.SheetsLogger')
@patch('utils.data_connector.create_connector')
def test_traider_init_paper_mode(
    mock_connector, mock_sheets, mock_g1, mock_g2, mock_g3, mock_reflector,
    mock_env, mock_bot_state, mock_mt5
):
    """Test TraiderMainLoop initializes broker in paper mode"""
    from main import TraiderMainLoop
    import argparse

    # Mock connector
    mock_conn = Mock()
    mock_conn.connect = Mock()
    mock_connector.return_value = mock_conn

    # Mock args
    args = argparse.Namespace(
        winrate_test=False,
        backtest=False,
        decision_engine='python'
    )

    # Initialize
    traider = TraiderMainLoop(args)

    # Check broker was created
    assert traider.broker is not None
    assert traider.broker.__class__.__name__ == 'PaperBroker'
    assert traider.broker.symbol == 'XAUUSDm'


@patch('agents.g4_reflector.Reflector')
@patch('agents.g3_python_decision.G3PythonDecision')
@patch('agents.g2_prefilter.G2Prefilter')
@patch('agents.g1_pattern_detector.G1PatternDetector')
@patch('agents.g4_sheets_logger.SheetsLogger')
@patch('utils.data_connector.create_connector')
def test_traider_init_micro_mode(
    mock_connector, mock_sheets, mock_g1, mock_g2, mock_g3, mock_reflector,
    mock_env
):
    """Test TraiderMainLoop doesn't create broker in micro mode"""
    from main import TraiderMainLoop
    import argparse

    # Mock bot_state with micro mode
    with patch('main.bot_state', {
        'mode': 'micro',
        'symbol': 'XAUUSDm',
        'trading_tf': 'M5'
    }):
        # Mock connector
        mock_conn = Mock()
        mock_conn.connect = Mock()
        mock_connector.return_value = mock_conn

        # Mock args
        args = argparse.Namespace(
            winrate_test=False,
            backtest=False,
            decision_engine='python'
        )

        # Initialize
        traider = TraiderMainLoop(args)

        # Check broker was NOT created
        assert traider.broker is None


# ============================================================================
# TEST ORDER EXECUTION
# ============================================================================

def test_broker_opens_positions_in_paper_mode(mock_mt5):
    """Test that orders are executed via broker in paper mode"""
    from agents.paper_broker import PaperBroker

    broker = PaperBroker(symbol='XAUUSDm')
    candle_time = datetime(2026, 4, 18, 10, 30, 0)

    # Simulate opening an order
    ticket = broker.open_position(
        action='BUY',
        lot=0.01,
        sl=3230.00,
        tp=3275.00,
        plan_id='PLAN-001',
        candle_time=candle_time,
        trade_id='TRD-001'
    )

    # Check ticket returned
    assert ticket is not None
    assert ticket >= 90000

    # Check position in broker
    positions = broker.get_open_positions()
    assert len(positions) == 1
    assert positions[0]['trade_id'] == 'TRD-001'
    assert positions[0]['action'] == 'BUY'


# ============================================================================
# TEST POSITION MONITORING
# ============================================================================

def test_broker_closes_positions_on_sl_hit(mock_mt5):
    """Test broker closes positions and returns newly_closed list"""
    from agents.paper_broker import PaperBroker

    broker = PaperBroker(symbol='XAUUSDm')
    candle_time = datetime(2026, 4, 18, 10, 30, 0)

    # Open BUY @ 3245.60, SL @ 3230
    broker.open_position('BUY', 0.01, 3230.00, 3275.00, 'PLAN-001', candle_time, 'TRD-001')

    # Price drops to SL
    mock_tick = Mock()
    mock_tick.bid = 3230.00
    mock_tick.ask = 3230.10
    mock_mt5.symbol_info_tick.return_value = mock_tick

    # Update positions
    newly_closed = broker.update_positions(candle_time)

    # Check closed
    assert len(newly_closed) == 1
    assert newly_closed[0]['result'] == 'LOSS'
    assert newly_closed[0]['close_reason'] == 'SL_HIT'
    assert newly_closed[0]['trade_id'] == 'TRD-001'


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
