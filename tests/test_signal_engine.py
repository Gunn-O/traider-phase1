"""
Unit Tests for Signal Engine (utils/signal_engine.py)

Tests:
1. convert_candles_to_ohlc - format conversion
2. run_signal_engine - with valid signal
3. run_signal_engine - with no signal (unclear)
4. mountain_state tracking
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from utils.signal_engine import convert_candles_to_ohlc, run_signal_engine, detect_session
from utils.xauusd_signal import OHLC, Signal


class TestSignalEngine(unittest.TestCase):
    """Test suite for Signal Engine"""

    def setUp(self):
        """Set up test fixtures"""
        # Mock M5 candles (55 candles)
        self.mock_candles = []
        base_time = datetime(2026, 4, 23, 12, 0, 0)
        base_price = 3240.0

        for i in range(55):
            self.mock_candles.append({
                'timestamp': base_time + timedelta(minutes=i * 5),
                'open': base_price + i * 0.10,
                'high': base_price + i * 0.10 + 0.50,
                'low': base_price + i * 0.10 - 0.30,
                'close': base_price + i * 0.10 + 0.20,
            })

        self.portfolio = 1000.0
        self.mountain_state = None

    def test_convert_candles_to_ohlc(self):
        """Test 1: Convert candles dict to OHLC format"""
        ohlc_bars = convert_candles_to_ohlc(self.mock_candles)

        # Check count
        self.assertEqual(len(ohlc_bars), 55)

        # Check first bar
        first = ohlc_bars[0]
        self.assertIsInstance(first, OHLC)
        self.assertEqual(first.bar_num, 1)
        self.assertEqual(first.open, 3240.0)
        self.assertEqual(first.high, 3240.5)
        self.assertEqual(first.low, 3239.7)
        self.assertEqual(first.close, 3240.2)

        # Check last bar
        last = ohlc_bars[-1]
        self.assertEqual(last.bar_num, 55)
        self.assertAlmostEqual(last.open, 3245.4, places=1)

    def test_run_signal_engine_with_signal(self):
        """Test 2: Run signal engine - valid signal returned"""
        candles_by_tf = {'M5': self.mock_candles}

        # Mock find_signal to return a valid signal
        mock_signal = Signal(
            pattern='DOWNTREND',
            direction='SELL',
            quality='100%✓',
            entry=3245.20,
            sl=3246.50,
            sl_name='SL1',
            tp_order=3243.00,
            tp_ref=3243.00,
            tp_name='TP1',
            rr=1.75,
            risk_pip=130,
            reward_pip=220,
            lot=0.77,
            R55=5.40
        )

        with patch('utils.signal_engine.find_signal', return_value=mock_signal):
            world_state = run_signal_engine(candles_by_tf, self.portfolio, self.mountain_state)

            # Verify world_state structure
            self.assertEqual(world_state['selected_tf'], 'M5')
            self.assertEqual(world_state['chart_type'], 'downtrend')
            self.assertEqual(world_state['quality'], 1.0)  # 100%✓ → 1.0
            self.assertEqual(world_state['technique_candidate'], 'twin_candle')

            # Verify signal was included
            self.assertIsNotNone(world_state['signal'])
            self.assertEqual(world_state['signal'], mock_signal)

            # Verify chart_detail has signal data
            detail = world_state['chart_detail']
            self.assertEqual(detail['pattern'], 'DOWNTREND')
            self.assertEqual(detail['direction'], 'SELL')
            self.assertEqual(detail['entry'], 3245.20)
            self.assertEqual(detail['sl'], 3246.50)
            self.assertEqual(detail['tp_order'], 3243.00)
            self.assertEqual(detail['rr'], 1.75)
            self.assertEqual(detail['lot'], 0.77)

    def test_run_signal_engine_no_signal(self):
        """Test 3: Run signal engine - no signal (unclear)"""
        candles_by_tf = {'M5': self.mock_candles}

        # Mock find_signal to return None (no setup found)
        with patch('utils.signal_engine.find_signal', return_value=None):
            world_state = run_signal_engine(candles_by_tf, self.portfolio, self.mountain_state)

            # Verify world_state for no signal
            self.assertEqual(world_state['selected_tf'], 'M5')
            self.assertEqual(world_state['chart_type'], 'unclear')
            self.assertEqual(world_state['quality'], 0.0)
            self.assertEqual(world_state['technique_candidate'], 'skip')

            # Verify signal is None
            self.assertIsNone(world_state['signal'])

            # Verify range is still calculated
            self.assertIn('range', world_state)
            self.assertGreater(world_state['range']['usd'], 0)

    def test_run_signal_engine_insufficient_data(self):
        """Test 4: Run signal engine - insufficient candles"""
        # Only 40 candles (less than 55)
        short_candles = self.mock_candles[:40]
        candles_by_tf = {'M5': short_candles}

        world_state = run_signal_engine(candles_by_tf, self.portfolio, self.mountain_state)

        # Verify world_state for insufficient data
        self.assertEqual(world_state['selected_tf'], 'M5')
        self.assertEqual(world_state['chart_type'], 'unclear')
        self.assertEqual(world_state['quality'], 0.0)
        self.assertIsNone(world_state['signal'])
        self.assertEqual(world_state['skip_reason'], 'insufficient_data')

    def test_mountain_state_tracking_round1(self):
        """Test 5: Mountain state tracking - Round 1"""
        candles_by_tf = {'M5': self.mock_candles}

        # Mock find_signal to return Mountain Round 1
        mock_signal = Signal(
            pattern='MOUNTAIN',
            direction='BUY',
            quality='100%✓',
            entry=3240.00,
            sl=3238.50,
            sl_name='SL1',
            tp_order=3241.50,
            tp_ref=3241.50,
            tp_name='TP1',
            rr=1.0,
            risk_pip=150,
            reward_pip=150,
            lot=0.67,
            R55=5.40,
            details={'peak': 3245.00}
        )

        with patch('utils.signal_engine.find_signal', return_value=mock_signal):
            world_state = run_signal_engine(candles_by_tf, self.portfolio, None)

            # Verify mountain_state was created
            mountain_state = world_state['mountain_state']
            self.assertIsNotNone(mountain_state)
            self.assertTrue(mountain_state['has_mountain_r1'])
            self.assertEqual(mountain_state['mountain_r1_entry'], 3240.00)
            self.assertEqual(mountain_state['mountain_r1_peak'], 3245.00)
            self.assertIn('mountain_r1_time', mountain_state)

    def test_mountain_state_tracking_round2(self):
        """Test 6: Mountain state tracking - Round 2"""
        candles_by_tf = {'M5': self.mock_candles}

        # Initial mountain state (from Round 1)
        existing_state = {
            'has_mountain_r1': True,
            'mountain_r1_time': '2026-04-23T12:00:00',
            'mountain_r1_entry': 3240.00,
            'mountain_r1_peak': 3245.00
        }

        # Mock find_signal to return Mountain Round 2
        mock_signal = Signal(
            pattern='MOUNTAIN_R2',
            direction='BUY',
            quality='100%✓',
            entry=3239.50,
            sl=3238.00,
            sl_name='SL1',
            tp_order=3241.00,
            tp_ref=3241.00,
            tp_name='TP1',
            rr=1.0,
            risk_pip=150,
            reward_pip=150,
            lot=0.67,
            R55=5.40
        )

        with patch('utils.signal_engine.find_signal', return_value=mock_signal):
            world_state = run_signal_engine(candles_by_tf, self.portfolio, existing_state)

            # Verify mountain_state was cleared after Round 2
            self.assertIsNone(world_state['mountain_state'])
            self.assertEqual(world_state['chart_type'], 'mountain_r2')

    def test_detect_session(self):
        """Test 7: Session detection from timestamp"""
        # Asia session: 00:00-08:00 UTC
        asia_time = datetime(2026, 4, 23, 5, 0, 0)
        self.assertEqual(detect_session(asia_time), 'asia')

        # London session: 08:00-12:00 UTC
        london_time = datetime(2026, 4, 23, 10, 0, 0)
        self.assertEqual(detect_session(london_time), 'london')

        # US session: 12:00-20:00 UTC
        us_time = datetime(2026, 4, 23, 15, 0, 0)
        self.assertEqual(detect_session(us_time), 'us')

        # US Close: 20:00-00:00 UTC
        us_close_time = datetime(2026, 4, 23, 22, 0, 0)
        self.assertEqual(detect_session(us_close_time), 'us_close')

        # Unknown (non-datetime)
        self.assertEqual(detect_session("not a datetime"), 'unknown')


if __name__ == '__main__':
    unittest.main()
