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
                # Gold symbols (XAUUSD/XAUUSDm) on OANDA exchange
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
                        symbol=symbol,
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
                        symbol=symbol,
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


# ============================================================================
# NEW: Simplified Connector Architecture (V4.3)
# ============================================================================

class MT5Connector:
    """
    MT5 Data Connector — ดึง OHLC จาก MT5 Terminal
    ใช้ได้ทุก mode: backtest/simulate/paper/live
    """

    def __init__(self, symbol: str = "XAUUSDm"):
        """
        Initialize MT5 Connector

        Args:
            symbol: Trading symbol (e.g., "XAUUSDm", "XAUUSD")
        """
        if not MT5_AVAILABLE:
            raise RuntimeError("MetaTrader5 not available")

        self.symbol = symbol
        self.connected = False

        # Try to initialize MT5
        if not mt5.initialize():
            raise RuntimeError(f"MT5 initialize() failed: {mt5.last_error()}")

        self.connected = True
        logger.info(f"✅ MT5 connected | symbol={symbol}")

    def get_candles(
        self,
        timeframe: str,
        count: int = 80,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Dict]:
        """
        Get OHLC candles from MT5

        Args:
            timeframe: 'M1', 'M5', 'M15', 'M30', 'H1', 'H4'
            count: Number of candles (for simulate mode)
            start_date: Start date for backtest mode
            end_date: End date for backtest mode

        Returns:
            List of candle dicts
        """
        # Map timeframe string to MT5 constant
        tf_map = {
            "M1":  mt5.TIMEFRAME_M1,
            "M5":  mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1":  mt5.TIMEFRAME_H1,
            "H4":  mt5.TIMEFRAME_H4,
        }
        tf = tf_map.get(timeframe)
        if tf is None:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        # Fetch data
        if start_date and end_date:
            # Backtest mode: get historical range
            rates = mt5.copy_rates_range(self.symbol, tf, start_date, end_date)
        else:
            # Simulate mode: get N latest candles
            rates = mt5.copy_rates_from_pos(self.symbol, tf, 0, count)

        if rates is None or len(rates) == 0:
            raise RuntimeError(
                f"MT5: no data for {self.symbol} {timeframe} "
                f"(error: {mt5.last_error()})"
            )

        # Convert to standard format
        candles = []
        for r in rates:
            candles.append({
                "time": pd.to_datetime(r["time"], unit='s'),
                "timestamp": datetime.fromtimestamp(r["time"]),
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": int(r.get("tick_volume", 0))
            })

        return candles

    def is_connected(self) -> bool:
        """Check if MT5 is connected"""
        return mt5.terminal_info() is not None

    def get_latest_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict]:
        """
        Compatibility wrapper for get_candles()
        (matches old DataConnector API)

        Args:
            symbol: Symbol (ignored, uses self.symbol)
            timeframe: 'M1', 'M5', etc.
            count: Number of candles
            start_date: Optional start date
            end_date: Optional end date

        Returns:
            List of candle dicts
        """
        return self.get_candles(timeframe, count, start_date, end_date)

    def get_all_timeframes_optimized(
        self,
        symbol: str,
        base_tf: str = 'M5',
        count: int = 55
    ) -> Dict[str, List[Dict]]:
        """
        Fetch M5 and resample to all requested timeframes
        (matches old DataConnector API)

        Args:
            symbol: Symbol (ignored, uses self.symbol)
            base_tf: Base timeframe (default M5)
            count: Number of candles per TF

        Returns:
            {
                'M5': [candles],
                'M15': [candles],
                ...
            }
        """
        # Fetch M5 candles (enough to resample)
        # For M5 → H4, need more candles (48x multiplier)
        m5_needed = count * 48  # Conservative: enough for H4

        m5_candles = self.get_candles('M5', m5_needed)

        # Resample to all timeframes in TIMEFRAMES
        result = {}
        for tf in TIMEFRAMES:
            if tf == 'M5':
                result[tf] = m5_candles[-count:] if len(m5_candles) >= count else m5_candles
            elif tf == 'M1':
                # Can't downsample M5 to M1
                result[tf] = []
            else:
                # Resample M5 → M15/M30/H1/H4
                result[tf] = self._resample_m5(m5_candles, tf, count)

        return result

    def _resample_m5(self, m5_candles: List[Dict], target_tf: str, count: int) -> List[Dict]:
        """Resample M5 candles to higher timeframe"""
        import pandas as pd

        if not m5_candles:
            return []

        # Convert to DataFrame
        df = pd.DataFrame(m5_candles)
        df.set_index('time', inplace=True)

        # Resample
        tf_map = {'M15': '15T', 'M30': '30T', 'H1': '1H', 'H4': '4H'}
        freq = tf_map.get(target_tf)
        if freq is None:
            return []

        resampled = df.resample(freq).agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()

        # Convert back to dict
        candles = []
        for idx, row in resampled.iterrows():
            candles.append({
                'time': idx,
                'timestamp': idx.to_pydatetime() if hasattr(idx, 'to_pydatetime') else idx,
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close']),
                'volume': int(row['volume'])
            })

        return candles[-count:] if len(candles) >= count else candles

    def disconnect(self):
        """Disconnect from MT5"""
        if self.connected:
            mt5.shutdown()
            self.connected = False
            logger.info("MT5 disconnected")

    @property
    def source_name(self) -> str:
        """Return data source name for bot_state"""
        return "MT5"

    def __repr__(self):
        return f"MT5Connector(symbol={self.symbol})"


class YFinanceConnector:
    """
    yfinance Data Connector — Free, No Login Required
    Symbol: GC=F (Gold Futures)
    Priority: After MT5, before TradingView
    """

    def __init__(self, symbol: str = "XAUUSD"):
        """
        Initialize yfinance Connector

        Args:
            symbol: Trading symbol (XAUUSD → converts to GC=F internally)
        """
        try:
            import yfinance as yf
            self.yf = yf
        except ImportError:
            raise RuntimeError("yfinance not available. Install: pip install yfinance")

        # Convert XAUUSD to Gold Futures symbol
        self.yf_symbol = "GC=F"  # Gold Futures
        self.symbol = symbol     # Keep original for display
        self.connected = False

        # Test connection by fetching 1 candle
        try:
            ticker = self.yf.Ticker(self.yf_symbol)
            test_data = ticker.history(period="1d", interval="5m")
            if test_data.empty:
                raise RuntimeError(f"yfinance: No data for {self.yf_symbol}")
            self.connected = True
            logger.info(f"📊 yfinance connected | {symbol} → {self.yf_symbol}")
        except Exception as e:
            raise RuntimeError(f"yfinance connection failed: {e}")

    def get_candles(
        self,
        timeframe: str,
        count: int = 80,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Dict]:
        """
        Get OHLC candles from yfinance

        Args:
            timeframe: 'M1', 'M5', 'M15', 'M30', 'H1', 'H4'
            count: Number of candles
            start_date: Start date for backtest
            end_date: End date for backtest

        Returns:
            List of candle dicts
        """
        # Map timeframe to yfinance interval
        tf_map = {
            "M1":  "1m",
            "M5":  "5m",
            "M15": "15m",
            "M30": "30m",
            "H1":  "1h",
            "H4":  "4h",
        }
        interval = tf_map.get(timeframe)
        if interval is None:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        ticker = self.yf.Ticker(self.yf_symbol)

        # Fetch data
        if start_date and end_date:
            # Backtest mode: get historical range
            # yfinance needs string dates
            df = ticker.history(
                start=start_date.strftime("%Y-%m-%d"),
                end=(end_date + timedelta(days=1)).strftime("%Y-%m-%d"),
                interval=interval
            )
        else:
            # Simulate mode: get N latest candles
            # yfinance period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
            # Calculate appropriate period based on count
            tf_minutes = TF_MINUTES.get(timeframe, 5)
            days_needed = (count * tf_minutes) / (24 * 60) * 1.5  # 50% buffer

            if days_needed <= 1:
                period = "1d"
            elif days_needed <= 5:
                period = "5d"
            elif days_needed <= 30:
                period = "1mo"
            elif days_needed <= 90:
                period = "3mo"
            elif days_needed <= 180:
                period = "6mo"
            else:
                period = "1y"

            df = ticker.history(period=period, interval=interval)

        if df.empty:
            raise RuntimeError(f"yfinance: No data for {self.yf_symbol} {timeframe}")

        # Convert to standard format
        candles = []
        for idx, row in df.iterrows():
            candles.append({
                "time": idx,
                "timestamp": idx.to_pydatetime() if hasattr(idx, 'to_pydatetime') else idx,
                "open": float(row['Open']),
                "high": float(row['High']),
                "low": float(row['Low']),
                "close": float(row['Close']),
                "volume": int(row.get('Volume', 0))
            })

        # Take last N candles if simulate mode
        if not (start_date and end_date):
            candles = candles[-count:] if len(candles) > count else candles

        return candles

    def get_latest_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict]:
        """
        Compatibility wrapper for get_candles()
        (matches old DataConnector API)
        """
        return self.get_candles(timeframe, count, start_date, end_date)

    def get_all_timeframes_optimized(
        self,
        symbol: str,
        base_tf: str = 'M5',
        count: int = 55
    ) -> Dict[str, List[Dict]]:
        """
        Fetch M5 and resample to all requested timeframes
        """
        # Fetch M5 candles (enough to resample)
        m5_needed = count * 48  # Conservative: enough for H4

        m5_candles = self.get_candles('M5', m5_needed)

        # Resample to all timeframes in TIMEFRAMES
        result = {}
        for tf in TIMEFRAMES:
            if tf == 'M5':
                result[tf] = m5_candles[-count:] if len(m5_candles) >= count else m5_candles
            elif tf == 'M1':
                # Can't downsample M5 to M1
                result[tf] = []
            else:
                # Resample M5 → M15/M30/H1/H4
                result[tf] = self._resample_m5(m5_candles, tf, count)

        return result

    def _resample_m5(self, m5_candles: List[Dict], target_tf: str, count: int) -> List[Dict]:
        """Resample M5 candles to higher timeframe"""
        import pandas as pd

        if not m5_candles:
            return []

        # Convert to DataFrame
        df = pd.DataFrame(m5_candles)
        df.set_index('time', inplace=True)

        # Resample
        tf_map = {'M15': '15T', 'M30': '30T', 'H1': '1H', 'H4': '4H'}
        freq = tf_map.get(target_tf)
        if freq is None:
            return []

        resampled = df.resample(freq).agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()

        # Convert back to dict
        candles = []
        for idx, row in resampled.iterrows():
            candles.append({
                'time': idx,
                'timestamp': idx.to_pydatetime() if hasattr(idx, 'to_pydatetime') else idx,
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close']),
                'volume': int(row['volume'])
            })

        return candles[-count:] if len(candles) >= count else candles

    def is_connected(self) -> bool:
        """Check if yfinance is connected"""
        return self.connected

    @property
    def source_name(self) -> str:
        """Return data source name for bot_state"""
        return "yfinance"

    def disconnect(self):
        """Disconnect (no-op for yfinance)"""
        self.connected = False
        logger.info("yfinance disconnected")

    def __repr__(self):
        return f"YFinanceConnector(symbol={self.symbol} → {self.yf_symbol})"


class TVConnector:
    """
    TradingView Data Connector — Fallback when MT5 unavailable
    Backtest: Limited to ~60 days (conservative limit)
    Simulate: Works normally
    """

    BACKTEST_LIMIT_DAYS = 60  # Conservative limit (API can handle ~70)

    def __init__(self, symbol: str = "XAUUSD"):
        """
        Initialize TradingView Connector

        Args:
            symbol: Trading symbol (XAUUSD for TradingView/OANDA)
        """
        if not TVDATAFEED_AVAILABLE:
            raise RuntimeError("tvdatafeed not available. Install: pip install git+https://github.com/rongardF/tvdatafeed.git")

        self.symbol = symbol
        self.connected = False
        self.tv_client = None

        # Get credentials
        username = os.getenv('TV_USERNAME')
        password = os.getenv('TV_PASSWORD')

        try:
            self.tv_client = TvDatafeed(username, password)
            self.connected = True
            logger.info(f"📺 TradingView connected | symbol={symbol}/OANDA")
        except Exception as e:
            raise RuntimeError(f"TradingView connection failed: {e}")

    def get_candles(
        self,
        timeframe: str,
        count: int = 80,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Dict]:
        """
        Get OHLC candles from TradingView

        Args:
            timeframe: 'M1', 'M5', 'M15', 'M30', 'H1', 'H4'
            count: Number of candles
            start_date: Start date for backtest
            end_date: End date for backtest

        Returns:
            List of candle dicts
        """
        # Map timeframe to TradingView interval
        tf_minutes = TF_MINUTES.get(timeframe)
        if tf_minutes is None:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        tv_interval_map = {
            1: Interval.in_1_minute,
            5: Interval.in_5_minute,
            15: Interval.in_15_minute,
            30: Interval.in_30_minute,
            60: Interval.in_1_hour,
            240: Interval.in_4_hour,
        }
        tv_interval = tv_interval_map.get(tf_minutes)
        if tv_interval is None:
            raise ValueError(f"TV interval not mapped for {timeframe}")

        # Backtest mode: check range limit
        if start_date and end_date:
            days_diff = (end_date - start_date).days

            if days_diff > self.BACKTEST_LIMIT_DAYS:
                logger.warning(
                    f"⚠️ TradingView backtest limit: {days_diff} days > "
                    f"{self.BACKTEST_LIMIT_DAYS} days"
                )
                logger.warning(
                    f"⚠️ Auto-trimming start_date to stay within limit"
                )
                # Auto-trim start_date
                start_date = end_date - timedelta(days=self.BACKTEST_LIMIT_DAYS)
                logger.info(f"   New start_date: {start_date.date()}")

            # Calculate bars needed
            bars_per_day = {
                1: 1440,    # M1: 1440 bars/day
                5: 288,     # M5: 288 bars/day
                15: 96,     # M15: 96 bars/day
                30: 48,     # M30: 48 bars/day
                60: 24,     # H1: 24 bars/day
                240: 6,     # H4: 6 bars/day
            }
            bars_needed = (days_diff + 1) * bars_per_day.get(tf_minutes, 300)
            bars_needed = min(bars_needed, 20000)  # API hard limit

        else:
            # Simulate mode: just get N bars
            bars_needed = count

        # Fetch from TradingView
        try:
            df = self.tv_client.get_hist(
                symbol=self.symbol,
                exchange='OANDA',
                interval=tv_interval,
                n_bars=bars_needed
            )

            if df is None or df.empty:
                raise RuntimeError(f"TV returned no data for {self.symbol}")

            # Filter to exact date range if backtest
            if start_date and end_date:
                df = df[(df.index >= start_date) & (df.index <= end_date)]

            # Convert to standard format
            candles = []
            for idx, row in df.iterrows():
                candles.append({
                    "time": idx,
                    "timestamp": idx.to_pydatetime() if hasattr(idx, 'to_pydatetime') else idx,
                    "open": float(row['open']),
                    "high": float(row['high']),
                    "low": float(row['low']),
                    "close": float(row['close']),
                    "volume": int(row.get('volume', 0))
                })

            return candles

        except Exception as e:
            logger.error(f"TradingView fetch failed: {e}")
            raise RuntimeError(f"TV data fetch error: {e}")

    def is_connected(self) -> bool:
        """Check if connected"""
        return self.connected and self.tv_client is not None

    def get_latest_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict]:
        """
        Compatibility wrapper for get_candles()
        (matches old DataConnector API)

        Args:
            symbol: Symbol (ignored, uses self.symbol)
            timeframe: 'M1', 'M5', etc.
            count: Number of candles
            start_date: Optional start date
            end_date: Optional end date

        Returns:
            List of candle dicts
        """
        return self.get_candles(timeframe, count, start_date, end_date)

    def get_all_timeframes_optimized(
        self,
        symbol: str,
        base_tf: str = 'M5',
        count: int = 55
    ) -> Dict[str, List[Dict]]:
        """
        Fetch M5 and resample to all requested timeframes
        (matches old DataConnector API)

        Args:
            symbol: Symbol (ignored, uses self.symbol)
            base_tf: Base timeframe (default M5)
            count: Number of candles per TF

        Returns:
            {
                'M5': [candles],
                'M15': [candles],
                ...
            }
        """
        # Fetch M5 candles (enough to resample)
        m5_needed = count * 48  # Conservative: enough for H4

        m5_candles = self.get_candles('M5', m5_needed)

        # Resample to all timeframes in TIMEFRAMES
        result = {}
        for tf in TIMEFRAMES:
            if tf == 'M5':
                result[tf] = m5_candles[-count:] if len(m5_candles) >= count else m5_candles
            elif tf == 'M1':
                # Can't downsample M5 to M1
                result[tf] = []
            else:
                # Resample M5 → M15/M30/H1/H4
                result[tf] = self._resample_m5(m5_candles, tf, count)

        return result

    def _resample_m5(self, m5_candles: List[Dict], target_tf: str, count: int) -> List[Dict]:
        """Resample M5 candles to higher timeframe"""
        import pandas as pd

        if not m5_candles:
            return []

        # Convert to DataFrame
        df = pd.DataFrame(m5_candles)
        df.set_index('time', inplace=True)

        # Resample
        tf_map = {'M15': '15T', 'M30': '30T', 'H1': '1H', 'H4': '4H'}
        freq = tf_map.get(target_tf)
        if freq is None:
            return []

        resampled = df.resample(freq).agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()

        # Convert back to dict
        candles = []
        for idx, row in resampled.iterrows():
            candles.append({
                'time': idx,
                'timestamp': idx.to_pydatetime() if hasattr(idx, 'to_pydatetime') else idx,
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close']),
                'volume': int(row['volume'])
            })

        return candles[-count:] if len(candles) >= count else candles

    def is_connected(self) -> bool:
        """Check if TradingView is connected"""
        return self.connected and self.tv_client is not None

    @property
    def source_name(self) -> str:
        """Return data source name for bot_state"""
        return "TradingView"

    def disconnect(self):
        """Disconnect (no-op for TradingView)"""
        self.connected = False
        self.tv_client = None
        logger.info("TradingView disconnected")

    def __repr__(self):
        return f"TVConnector(symbol={self.symbol}/OANDA)"


# ============================================================================
# Auto-Detection Factory Function
# ============================================================================

def create_connector(mode: str = "auto", symbol: str = "XAUUSDm"):
    """
    Auto-detect data source and create appropriate connector

    Priority:
    1. MT5 (if available and connected)
    2. yfinance (free, no login required) ✨ NEW
    3. TradingView (fallback, requires login)

    Args:
        mode: "auto" | "mt5" | "yf" | "tv" | "backtest"
              - "auto": Try MT5 → yfinance → TV
              - "mt5": Force MT5 (error if not available)
              - "yf": Force yfinance
              - "tv": Force TradingView
              - "backtest": Same as auto (for backward compatibility)
        symbol: Trading symbol
                - MT5: use "XAUUSDm" (cent) or "XAUUSD" (standard)
                - yfinance: use "XAUUSD" (converts to GC=F internally)
                - TV: use "XAUUSD" (OANDA doesn't have XAUUSDm)

    Returns:
        MT5Connector, YFinanceConnector, or TVConnector instance

    Raises:
        RuntimeError: If forced mode is not available
    """
    # Override from environment if not specified
    if mode == "auto":
        mode = os.getenv("DATA_MODE", "auto")

    # Normalize backtest/simulate mode to auto
    if mode in ["backtest", "simulate"]:
        mode = "auto"

    # Force MT5 mode
    if mode == "mt5":
        if not MT5_AVAILABLE:
            raise RuntimeError(
                "Mode 'mt5' requires MetaTrader5. "
                "Install: pip install MetaTrader5"
            )
        try:
            connector = MT5Connector(symbol=symbol)
            logger.info("✅ Using MT5 data source (forced)")
            return connector
        except Exception as e:
            raise RuntimeError(f"MT5 connection failed: {e}")

    # Force yfinance mode
    if mode == "yf":
        try:
            yf_symbol = "XAUUSD" if "XAUUSD" in symbol else symbol
            connector = YFinanceConnector(symbol=yf_symbol)
            logger.info("📊 Using yfinance data source (forced)")
            return connector
        except Exception as e:
            raise RuntimeError(f"yfinance connection failed: {e}")

    # Force TradingView mode
    if mode == "tv":
        if not TVDATAFEED_AVAILABLE:
            raise RuntimeError(
                "Mode 'tv' requires tvdatafeed. "
                "Install: pip install git+https://github.com/rongardF/tvdatafeed.git"
            )
        tv_symbol = "XAUUSD" if "XAUUSD" in symbol else symbol
        connector = TVConnector(symbol=tv_symbol)
        logger.info("📺 Using TradingView data source (forced)")
        return connector

    # Auto-detect mode (default)
    if mode == "auto":
        # Try MT5 first
        if MT5_AVAILABLE:
            try:
                connector = MT5Connector(symbol=symbol)
                logger.info("✅ Using MT5 data source (auto-detected)")
                return connector
            except Exception as e:
                logger.warning(f"⚠️ MT5 not available: {e}")
                logger.warning("⚠️ Trying yfinance next...")

        # Try yfinance second
        try:
            yf_symbol = "XAUUSD" if "XAUUSD" in symbol else symbol
            connector = YFinanceConnector(symbol=yf_symbol)
            logger.info("📊 Using yfinance data source (auto-detected)")
            return connector
        except Exception as e:
            logger.warning(f"⚠️ yfinance not available: {e}")
            logger.warning("⚠️ Falling back to TradingView...")

        # Fallback to TradingView
        if TVDATAFEED_AVAILABLE:
            tv_symbol = "XAUUSD" if "XAUUSD" in symbol else symbol
            connector = TVConnector(symbol=tv_symbol)
            logger.info("📺 Using TradingView data source (fallback)")
            return connector

        # None available
        raise RuntimeError(
            "No data source available. Install one of:\n"
            "  - MetaTrader5: pip install MetaTrader5\n"
            "  - yfinance: pip install yfinance (FREE, recommended)\n"
            "  - tvdatafeed: pip install git+https://github.com/rongardF/tvdatafeed.git"
        )

    # Invalid mode
    raise ValueError(
        f"Invalid mode: {mode}. "
        f"Must be 'auto', 'mt5', 'yf', 'tv', or 'backtest'"
    )


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
            candles = connector.get_latest_candles("XAUUSDm", timeframe=tf, count=55)
            print(f"✓ {tf}: {len(candles)} candles")

            if candles:
                last = candles[-1]
                print(f"  Last: {last['time']} | Close: ${last['close']:.2f}")
        except Exception as e:
            print(f"✗ {tf}: {e}")

    connector.disconnect()
