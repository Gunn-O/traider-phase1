"""
Data Connector - รองรับ 3 modes: backtest, simulate, live
- backtest: yfinance historical data (⚠️ Limitation: intraday data max 60 days)
- simulate: yfinance near real-time (delay ~15 min) - RECOMMENDED for development
- live: MetaTrader5 real-time data (Windows only)

⚠️ IMPORTANT: yfinance intraday data limitations:
- 5m/15m/30m: Last 60 days only
- 1h: Last 730 days only
- For historical backtesting beyond 60 days, use daily data or CSV files
"""

import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import pandas as pd
import numpy as np

# Mode-specific imports
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    print("Warning: yfinance not installed - backtest/simulate modes unavailable")

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
    - backtest: Historical data จาก yfinance สำหรับ backtesting
    - simulate: Real-time data จาก TradingView (accurate spot prices) ✨ RECOMMENDED
    - live: Real-time data จาก MetaTrader5 (Windows only, Phase II)

    Symbol Mapping:
    - yfinance: XAUUSD → GC=F (Gold Futures, ~$25 premium)
    - TradingView: XAUUSD/OANDA (Spot prices, accurate)
    """

    # Symbol mapping สำหรับ yfinance (backtest mode)
    SYMBOL_MAP = {
        "XAUUSD": "GC=F",  # Gold Futures
        "EURUSD": "EURUSD=X",
        "GBPUSD": "GBPUSD=X",
        "USDJPY": "USDJPY=X",
    }

    # Timeframe mapping สำหรับ yfinance
    YF_INTERVAL_MAP = {
        1: "1m",
        5: "5m",
        15: "15m",
        30: "30m",
        60: "1h",
        240: "4h",
        1440: "1d"
    }

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

    def __init__(self, mode: str = "backtest"):
        """
        Initialize DataConnector

        Args:
            mode: "backtest" | "simulate" | "live"
        """
        if mode not in ["backtest", "simulate", "live"]:
            raise ValueError(f"Invalid mode: {mode}. Must be 'backtest', 'simulate', or 'live'")

        self.mode = mode
        self.connected = False
        self.tv_client = None  # TradingView client instance

        # Validate dependencies
        if mode == "backtest" and not YFINANCE_AVAILABLE:
            raise RuntimeError("Mode 'backtest' requires yfinance. Install: pip install yfinance")

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
            # backtest mode (yfinance) ไม่ต้อง connect
            self.connected = True
            return True

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
                    start_date: Optional[datetime] = None,
                    end_date: Optional[datetime] = None) -> pd.DataFrame:
        """
        Get OHLCV candles

        Args:
            symbol: Symbol name (e.g., "XAUUSD")
            timeframe: Timeframe in minutes (5, 15, 60, etc.)
            count: Number of candles to retrieve
            start_date: Start date (for backtest mode)
            end_date: End date (for backtest mode)

        Returns:
            DataFrame with columns: time, open, high, low, close, volume
        """
        if not self.connected:
            raise RuntimeError("Not connected. Call connect() first.")

        if self.mode == "live":
            return self._get_candles_mt5(symbol, timeframe, count)
        elif self.mode == "simulate":
            return self._get_candles_tradingview(symbol, timeframe, count)
        else:  # backtest
            return self._get_candles_yfinance(symbol, timeframe, count, start_date, end_date)

    def _get_candles_yfinance(self, symbol: str, timeframe: int, count: int,
                               start_date: Optional[datetime] = None,
                               end_date: Optional[datetime] = None) -> pd.DataFrame:
        """Get candles from yfinance"""

        # Map symbol
        yf_symbol = self.SYMBOL_MAP.get(symbol, symbol)

        # Map interval
        yf_interval = self.YF_INTERVAL_MAP.get(timeframe)
        if not yf_interval:
            raise ValueError(f"Unsupported timeframe: {timeframe} minutes")

        # Calculate date range
        if self.mode == "backtest":
            if not start_date or not end_date:
                raise ValueError("backtest mode requires start_date and end_date")

            # Check yfinance limitations
            days_ago = (datetime.now() - start_date).days
            if timeframe <= 30 and days_ago > 60:
                print(f"\n⚠️  WARNING: yfinance limitation detected!")
                print(f"   Timeframe: {timeframe}m, Date: {start_date.date()}")
                print(f"   yfinance only provides 5m/15m/30m data for last 60 days")
                print(f"   Your request is {days_ago} days ago")
                print(f"\n💡 Solutions:")
                print(f"   1. Use 'simulate' mode for recent 60 days (RECOMMENDED)")
                print(f"   2. Use hourly (60m) or daily data for historical backtest")
                print(f"   3. Download and save data as CSV, then load from file")
                raise ValueError(f"Intraday data not available for {days_ago} days ago (limit: 60 days)")

            period = None
        else:  # simulate mode
            # Get recent data (period based on timeframe and count)
            if timeframe <= 60:  # intraday
                # yfinance มีข้อจำกัด 60 วันสำหรับ intraday data
                period = "60d"
                end_date = datetime.now()
                start_date = end_date - timedelta(days=60)
            else:
                period = "60d"
                end_date = datetime.now()
                start_date = end_date - timedelta(days=60)

        try:
            ticker = yf.Ticker(yf_symbol)

            if period:
                df = ticker.history(period=period, interval=yf_interval)
            else:
                df = ticker.history(start=start_date, end=end_date, interval=yf_interval)

            if df.empty:
                print(f"Warning: No data retrieved for {yf_symbol}")
                return pd.DataFrame(columns=['time', 'open', 'high', 'low', 'close', 'volume'])

            # Rename columns และจัด format
            df = df.reset_index()
            df = df.rename(columns={
                'Date': 'time' if 'Date' in df.columns else 'Datetime',
                'Datetime': 'time',
                'Open': 'open',
                'High': 'high',
                'Low': 'low',
                'Close': 'close',
                'Volume': 'volume'
            })

            # เลือกเฉพาะ columns ที่ต้องการ
            df = df[['time', 'open', 'high', 'low', 'close', 'volume']]

            # Get last N candles
            df = df.tail(count)

            # Reset index
            df = df.reset_index(drop=True)

            return df

        except Exception as e:
            print(f"Error fetching data from yfinance: {e}")
            return pd.DataFrame(columns=['time', 'open', 'high', 'low', 'close', 'volume'])

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

    def _get_candles_tradingview(self, symbol: str, timeframe: int, count: int) -> pd.DataFrame:
        """Get candles from TradingView"""

        if not self.tv_client:
            raise RuntimeError("TradingView client not initialized")

        # Map interval
        tv_interval = self.TV_INTERVAL_MAP.get(timeframe)
        if tv_interval is None:
            raise ValueError(f"Unsupported timeframe: {timeframe} minutes")

        try:
            # Get data from TradingView
            # XAUUSD on OANDA exchange
            df = self.tv_client.get_hist(
                symbol='XAUUSD',
                exchange='OANDA',
                interval=tv_interval,
                n_bars=count
            )

            if df is None or df.empty:
                print(f"Warning: No data retrieved for {symbol}")
                return pd.DataFrame(columns=['time', 'open', 'high', 'low', 'close', 'volume'])

            # Reset index (datetime → column)
            df = df.reset_index()

            # Rename columns
            df = df.rename(columns={
                'datetime': 'time'
            })

            # เลือกเฉพาะ columns ที่ต้องการ
            df = df[['time', 'open', 'high', 'low', 'close', 'volume']]

            return df

        except Exception as e:
            print(f"Error fetching data from TradingView: {e}")
            return pd.DataFrame(columns=['time', 'open', 'high', 'low', 'close', 'volume'])

    def get_latest_candles(self, symbol: str, m5_count: int = 80, h1_count: int = 20,
                          start_date: Optional[datetime] = None,
                          end_date: Optional[datetime] = None) -> Dict:
        """
        Get latest candles for both M5 and H1 timeframes

        Args:
            symbol: Symbol name (e.g., "XAUUSD")
            m5_count: Number of M5 candles (default: 80)
            h1_count: Number of H1 candles (default: 20)
            start_date: Start date (backtest mode only)
            end_date: End date (backtest mode only)

        Returns:
            Dict with keys: m5_ohlcv, h1_candles, current_price, timestamp
        """
        # Get M5 data
        m5_data = self.get_candles(symbol, 5, m5_count, start_date, end_date)

        # Get H1 data
        h1_data = self.get_candles(symbol, 60, h1_count, start_date, end_date)

        if m5_data.empty:
            raise RuntimeError(f"Failed to get M5 data for {symbol}")

        # Current price = last M5 close
        current_price = float(m5_data.iloc[-1]['close'])
        timestamp = m5_data.iloc[-1]['time']

        return {
            "m5_ohlcv": m5_data.to_dict('records'),
            "h1_candles": h1_data.to_dict('records') if not h1_data.empty else [],
            "current_price": current_price,
            "timestamp": timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp),
            "symbol": symbol
        }

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

    # Test backtest mode
    print("\n=== Testing BACKTEST mode ===")
    connector = DataConnector(mode="backtest")
    connector.connect()

    start = datetime(2025, 1, 1)
    end = datetime(2025, 1, 31)

    data = connector.get_latest_candles("XAUUSD", m5_count=80, h1_count=20,
                                       start_date=start, end_date=end)

    print(f"Symbol: {data['symbol']}")
    print(f"Timestamp: {data['timestamp']}")
    print(f"Current price: {data['current_price']}")
    print(f"M5 candles: {len(data['m5_ohlcv'])}")
    print(f"H1 candles: {len(data['h1_candles'])}")

    if data['m5_ohlcv']:
        print(f"\nLast M5 candle: {data['m5_ohlcv'][-1]}")

    connector.disconnect()

    # Test simulate mode
    print("\n=== Testing SIMULATE mode ===")
    with create_connector("simulate") as conn:
        data = conn.get_latest_candles("XAUUSD", m5_count=20, h1_count=10)
        print(f"Current price: {data['current_price']}")
        print(f"M5 candles: {len(data['m5_ohlcv'])}")
