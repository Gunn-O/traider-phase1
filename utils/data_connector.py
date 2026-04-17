"""
Data Connector - รองรับ 2 modes: simulate, live
- simulate: TradingView real-time data (accurate spot prices) ✨ RECOMMENDED
- live: MetaTrader5 real-time data (Windows only, Phase II)
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# Import TIMEFRAMES from config (for Single TF / MTF selection)
try:
    from config import TIMEFRAMES
except ImportError:
    # Fallback if config not available (shouldn't happen in normal use)
    TIMEFRAMES = ['M5']
    logger.warning("Could not import TIMEFRAMES from config, using default ['M5']")

# Timeframe mapping (string → minutes)
TF_MINUTES = {
    'H4': 240,
    'H1': 60,
    'M30': 30,
    'M15': 15,
    'M5': 5,
    'M1': 1
}

# Mode-specific imports
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    print("Warning: MetaTrader5 not installed - live mode unavailable")

try:
    from tvDatafeed.main import TvDatafeed, Interval
    TVDATAFEED_AVAILABLE = True
except ImportError:
    TVDATAFEED_AVAILABLE = False
    print("Warning: tvdatafeed not installed - TradingView mode unavailable")


class DataConnector:
    """
    Data connector สำหรับ Tra(i)der Phase I

    Modes:
    - simulate: Real-time data จาก TradingView (XAUUSD/OANDA, accurate spot prices) ✨ RECOMMENDED
    - live: Real-time data จาก MetaTrader5 (Windows only, Phase II)
    """

    # Timeframe mapping สำหรับ TradingView
    if TVDATAFEED_AVAILABLE:
        TV_INTERVAL_MAP = {
            1: Interval.in_1_minute,
            5: Interval.in_5_minute,
            15: Interval.in_15_minute,
            30: Interval.in_30_minute,
            60: Interval.in_1_hour,
            240: Interval.in_4_hour,
            1440: Interval.in_daily
        }
    else:
        TV_INTERVAL_MAP = {}

    # Timeframe mapping สำหรับ MT5
    MT5_TIMEFRAME_MAP = {
        1: mt5.TIMEFRAME_M1 if MT5_AVAILABLE else None,
        5: mt5.TIMEFRAME_M5 if MT5_AVAILABLE else None,
        15: mt5.TIMEFRAME_M15 if MT5_AVAILABLE else None,
        30: mt5.TIMEFRAME_M30 if MT5_AVAILABLE else None,
        60: mt5.TIMEFRAME_H1 if MT5_AVAILABLE else None,
        240: mt5.TIMEFRAME_H4 if MT5_AVAILABLE else None,
        1440: mt5.TIMEFRAME_D1 if MT5_AVAILABLE else None,
    }

    def __init__(self, mode: str = "simulate"):
        """
        Initialize DataConnector

        Args:
            mode: "simulate" | "live"
        """
        if mode not in ["simulate", "live"]:
            raise ValueError(f"Invalid mode: {mode}. Must be 'simulate' or 'live'")

        self.mode = mode
        self.connected = False
        self.tv_client = None  # TradingView client instance

        # Validate dependencies
        if mode == "simulate" and not TVDATAFEED_AVAILABLE:
            raise RuntimeError("Mode 'simulate' requires tvdatafeed. Install: pip install git+https://github.com/rongardF/tvdatafeed.git")

        if mode == "live" and not MT5_AVAILABLE:
            raise RuntimeError("Mode 'live' requires MetaTrader5. Install: pip install MetaTrader5")

        print(f"DataConnector initialized in '{mode}' mode")

    def connect(self, **kwargs) -> bool:
        """
        Connect to data source

        Args:
            For live mode:
                - login: MT5 login
                - password: MT5 password
                - server: MT5 server
            For simulate mode (TradingView):
                - tv_username: TradingView username
                - tv_password: TradingView password

        Returns:
            True if connected successfully
        """
        if self.mode == "live":
            return self._connect_mt5(**kwargs)
        elif self.mode == "simulate":
            return self._connect_tradingview(**kwargs)
        else:
            raise ValueError(f"Unknown mode: {self.mode}")

    def _connect_mt5(self, login: Optional[int] = None,
                     password: Optional[str] = None,
                     server: Optional[str] = None) -> bool:
        """Connect to MetaTrader5"""
        if not MT5_AVAILABLE:
            raise RuntimeError("MetaTrader5 not available")

        # Initialize MT5
        if not mt5.initialize():
            print(f"MT5 initialize() failed, error: {mt5.last_error()}")
            return False

        # Login if credentials provided
        if login and password and server:
            if not mt5.login(login, password, server):
                print(f"MT5 login failed, error: {mt5.last_error()}")
                mt5.shutdown()
                return False
            print(f"MT5 connected to {server} (account {login})")
        else:
            print("MT5 initialized (using terminal credentials)")

        self.connected = True
        return True

    def _connect_tradingview(self, tv_username: Optional[str] = None,
                             tv_password: Optional[str] = None) -> bool:
        """Connect to TradingView"""
        if not TVDATAFEED_AVAILABLE:
            raise RuntimeError("tvdatafeed not available")

        # Get credentials from kwargs or environment
        username = tv_username or os.getenv('TV_USERNAME')
        password = tv_password or os.getenv('TV_PASSWORD')

        try:
            # Create TradingView client
            self.tv_client = TvDatafeed(username, password)
            self.connected = True
            print(f"TradingView connected (username: {username})")

            # Verify XAUUSD price
            try:
                test_df = self.tv_client.get_hist(
                    symbol='XAUUSD',
                    exchange='OANDA',
                    interval=Interval.in_1_hour,
                    n_bars=1
                )
                if test_df is not None and not test_df.empty:
                    last_price = test_df['close'].iloc[-1]
                    print(f"✓ XAUUSD/OANDA spot price: ${last_price:.2f}")
                    print(f"  (This matches MT5 XAUUSD — suitable for backtest comparison)")
                else:
                    print("⚠️  Could not verify XAUUSD price")
            except:
                pass  # Ignore verification errors

            return True
        except Exception as e:
            print(f"TradingView connection failed: {e}")
            return False

    def disconnect(self):
        """Disconnect from data source"""
        if self.mode == "live" and MT5_AVAILABLE and self.connected:
            mt5.shutdown()
            print("MT5 disconnected")
        self.connected = False

    def get_candles(self, symbol: str, timeframe: int, count: int,
                    start_date=None, end_date=None) -> pd.DataFrame:
        """
        Get OHLCV candles

        Args:
            symbol: Symbol name (e.g., "XAUUSD")
            timeframe: Timeframe in minutes (5, 15, 60, etc.)
            count: Number of candles to retrieve (None for date range mode)
            start_date: Optional start datetime for backtest
            end_date: Optional end datetime for backtest

        Returns:
            DataFrame with columns: time, open, high, low, close, volume
        """
        if not self.connected:
            raise RuntimeError("Not connected. Call connect() first.")

        if self.mode == "live":
            return self._get_candles_mt5(symbol, timeframe, count)
        elif self.mode == "simulate":
            return self._get_candles_tradingview(symbol, timeframe, count, start_date, end_date)
        else:
            raise ValueError(f"Unknown mode: {self.mode}")

    def _get_candles_mt5(self, symbol: str, timeframe: int, count: int) -> pd.DataFrame:
        """Get candles from MetaTrader5"""

        # Map timeframe
        mt5_timeframe = self.MT5_TIMEFRAME_MAP.get(timeframe)
        if mt5_timeframe is None:
            raise ValueError(f"Unsupported timeframe: {timeframe} minutes")

        try:
            # Get candles
            rates = mt5.copy_rates_from_pos(symbol, mt5_timeframe, 0, count)

            if rates is None or len(rates) == 0:
                print(f"Warning: No data retrieved for {symbol}")
                return pd.DataFrame(columns=['time', 'open', 'high', 'low', 'close', 'volume'])

            # Convert to DataFrame
            df = pd.DataFrame(rates)

            # Convert time to datetime
            df['time'] = pd.to_datetime(df['time'], unit='s')

            # เลือกเฉพาะ columns ที่ต้องการ
            df = df[['time', 'open', 'high', 'low', 'close', 'tick_volume']]
            df = df.rename(columns={'tick_volume': 'volume'})

            return df

        except Exception as e:
            print(f"Error fetching data from MT5: {e}")
            return pd.DataFrame(columns=['time', 'open', 'high', 'low', 'close', 'volume'])

    def _get_candles_tradingview(self, symbol: str, timeframe: int, count: int,
                                  start_date=None, end_date=None) -> pd.DataFrame:
        """Get candles from TradingView with retry logic"""

        if not self.tv_client:
            raise RuntimeError("TradingView client not initialized")

        # Map interval
        tv_interval = self.TV_INTERVAL_MAP.get(timeframe)
        if tv_interval is None:
            raise ValueError(f"Unsupported timeframe: {timeframe} minutes")

        # Retry logic
        max_retries = 3
        retry_delay = 2  # seconds

        for attempt in range(max_retries):
            try:
                # Get data from TradingView
                # XAUUSD on OANDA exchange
                if start_date and end_date:
                    # Date range mode for backtest
                    # Calculate number of bars needed
                    days_diff = (end_date - start_date).days + 1
                    # M5: 288 candles/day (24h * 60min / 5min) for XAUUSD (24/5 market)
                    # Use generous estimate to account for weekends and market gaps
                    bars_needed = days_diff * 300  # 300 bars per day to be safe

                    # TradingView can handle large requests, cap at 20000 (~70 days for M5)
                    # If need longer backtests, consider fetching in chunks
                    if bars_needed > 20000:
                        logger.warning(f"⚠️  Requesting {bars_needed} bars (>{days_diff} days), capping at 20000")
                        logger.warning("For backtests >70 days, data may be incomplete at the start")
                        bars_needed = 20000

                    df = self.tv_client.get_hist(
                        symbol='XAUUSD',
                        exchange='OANDA',
                        interval=tv_interval,
                        n_bars=bars_needed
                    )

                    # Filter to exact date range
                    if df is not None and not df.empty:
                        df = df[df.index >= start_date]
                        df = df[df.index <= end_date]
                else:
                    # Count mode for live/regular use
                    df = self.tv_client.get_hist(
                        symbol='XAUUSD',
                        exchange='OANDA',
                        interval=tv_interval,
                        n_bars=count
                    )

                if df is None or df.empty:
                    if attempt < max_retries - 1:
                        print(f"⚠️  Retry {attempt + 1}/{max_retries}: No data, retrying in {retry_delay}s...")
                        import time
                        time.sleep(retry_delay)
                        continue
                    else:
                        print(f"Warning: No data retrieved for {symbol} after {max_retries} attempts")
                        return pd.DataFrame(columns=['time', 'open', 'high', 'low', 'close', 'volume'])

                # Success - Reset index (datetime → column)
                df = df.reset_index()

                # Rename columns
                df = df.rename(columns={
                    'datetime': 'time'
                })

                # เลือกเฉพาะ columns ที่ต้องการ
                df = df[['time', 'open', 'high', 'low', 'close', 'volume']]

                return df

            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"⚠️  Retry {attempt + 1}/{max_retries}: {str(e)[:50]}...")
                    import time
                    time.sleep(retry_delay)
                    continue
                else:
                    print(f"Error fetching data from TradingView after {max_retries} attempts: {e}")
                    return pd.DataFrame(columns=['time', 'open', 'high', 'low', 'close', 'volume'])

    def get_latest_candles(self, symbol: str, timeframe: str, count: int,
                           start_date=None, end_date=None) -> List[Dict]:
        """
        Get latest candles for specified timeframe (MTF support)

        Args:
            symbol: Symbol name (e.g., "XAUUSD")
            timeframe: Timeframe string ('H4', 'H1', 'M30', 'M15', 'M5', 'M1')
            count: Number of candles to retrieve (None for date range mode)
            start_date: Optional start datetime for backtest
            end_date: Optional end datetime for backtest

        Returns:
            List of candle dicts: [{'time', 'open', 'high', 'low', 'close', 'volume', 'timestamp'}, ...]
        """
        # Map timeframe to minutes
        tf_minutes = TF_MINUTES.get(timeframe)
        if tf_minutes is None:
            raise ValueError(f"Invalid timeframe: {timeframe}. Must be one of {list(TF_MINUTES.keys())}")

        # Get candles
        df = self.get_candles(symbol, tf_minutes, count, start_date=start_date, end_date=end_date)

        if df.empty:
            return []

        # Add timestamp column
        candles = df.to_dict('records')
        for candle in candles:
            # Use 'time' column as timestamp (already datetime from _get_candles_tradingview)
            if 'time' in candle and isinstance(candle['time'], pd.Timestamp):
                candle['timestamp'] = candle['time'].to_pydatetime()
            elif 'time' in candle:
                candle['timestamp'] = candle['time']
            else:
                # Fallback: use current time (should not happen)
                candle['timestamp'] = datetime.now()

        return candles

    def get_current_price(self, symbol: str) -> Optional[float]:
        """
        Get current price (bid)

        Args:
            symbol: Symbol name

        Returns:
            Current price or None if failed
        """
        if not self.connected:
            raise RuntimeError("Not connected")

        if self.mode == "live":
            tick = mt5.symbol_info_tick(symbol)
            if tick:
                return tick.bid
            return None
        else:
            # yfinance: get latest candle close
            df = self.get_candles(symbol, 5, 1)
            if not df.empty:
                return float(df.iloc[-1]['close'])
            return None

    def get_all_timeframes_optimized(self, symbol: str, base_tf: str = 'M5',
                                      count: int = 55) -> Dict[str, List[Dict]]:
        """
        Optimized: Fetch M5 once, resample to requested timeframes
        (respects TIMEFRAMES from config.py for Single TF / MTF mode)

        Args:
            symbol: Symbol name
            base_tf: Base timeframe to fetch (default M5)
            count: Number of candles needed per TF

        Returns:
            {
                'M5': [candles],  # if TIMEFRAMES = ['M5']
                or
                'H4': [candles], 'H1': [candles], ...  # if MTF mode
            }
        """
        if not self.connected:
            raise RuntimeError("Not connected")

        # Filter: only resample TFs that are >= M5 (can't downsample to M1 from M5)
        resample_tfs = [tf for tf in TIMEFRAMES if tf != 'M1']

        # If only M1 requested, skip resampling (will fetch M1 separately below)
        if not resample_tfs:
            result = {}
        else:
            # Calculate max bars needed (for largest TF in TIMEFRAMES)
            # H4 = 240 min = 48 M5 bars per H4 bar
            max_multiplier = max([TF_MINUTES.get(tf, 5) // 5 for tf in resample_tfs])
            max_bars_needed = count * max_multiplier

            # Fetch M5 data once
            m5_minutes = TF_MINUTES['M5']
            m5_df = self.get_candles(symbol, m5_minutes, max_bars_needed)

            if m5_df.empty:
                return {}

            # Ensure 'time' is datetime index for resampling
            if 'time' in m5_df.columns:
                m5_df = m5_df.set_index('time')

            # Resample to requested timeframes (from config.py)
            result = {}

            for tf in resample_tfs:
                if tf == 'M5':
                    # Use original M5 data
                    df_resampled = m5_df.copy()
                else:
                    # Resample
                    freq = f'{TF_MINUTES[tf]}min'
                    df_resampled = m5_df.resample(freq).agg({
                        'open': 'first',
                        'high': 'max',
                        'low': 'min',
                        'close': 'last',
                        'volume': 'sum'
                    }).dropna()

                # Take last `count` bars
                df_final = df_resampled.tail(count).reset_index()

                # Convert to list of dicts
                candles = df_final.to_dict('records')
                for candle in candles:
                    if 'time' in candle and isinstance(candle['time'], pd.Timestamp):
                        candle['timestamp'] = candle['time'].to_pydatetime()
                    else:
                        candle['timestamp'] = candle.get('time', datetime.now())

                result[tf] = candles

        # M1 needs separate fetch (can't downsample from M5)
        if 'M1' in TIMEFRAMES:
            try:
                m1_candles = self.get_latest_candles(symbol, 'M1', count)
                result['M1'] = m1_candles
            except:
                result['M1'] = []

        return result

    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()


# Helper function
def create_connector(mode: Optional[str] = None) -> DataConnector:
    """
    Factory function to create DataConnector from environment

    Args:
        mode: Override mode (optional). If None, read from DATA_MODE env var

    Returns:
        DataConnector instance
    """
    if mode is None:
        mode = os.getenv("DATA_MODE", "backtest")

    return DataConnector(mode=mode)


# Example usage
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    # Test simulate mode with new MTF API
    print("\n=== Testing SIMULATE mode (MTF) ===")
    connector = DataConnector(mode="simulate")
    connector.connect()

    # Test all 6 timeframes
    timeframes = ['H4', 'H1', 'M30', 'M15', 'M5', 'M1']

    for tf in timeframes:
        try:
            candles = connector.get_latest_candles("XAUUSD", timeframe=tf, count=55)
            print(f"✓ {tf}: {len(candles)} candles")

            if candles:
                last = candles[-1]
                print(f"  Last: {last['time']} | Close: ${last['close']:.2f}")
        except Exception as e:
            print(f"✗ {tf}: {e}")

    connector.disconnect()
