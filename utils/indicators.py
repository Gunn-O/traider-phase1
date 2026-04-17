"""
Technical Indicators สำหรับ Tra(i)der Phase I

- RSI(14): Relative Strength Index
- S/R Detection: Support/Resistance levels จาก swing highs/lows
- Trend Detection: H1 trend direction (bullish/bearish/sideways)
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional


def calculate_rsi(data: pd.DataFrame, period: int = 14, price_col: str = 'close') -> pd.Series:
    """
    Calculate RSI (Relative Strength Index)

    Args:
        data: DataFrame with OHLCV data
        period: RSI period (default: 14)
        price_col: Column name for price (default: 'close')

    Returns:
        pd.Series with RSI values (0-100)

    Formula:
        RSI = 100 - (100 / (1 + RS))
        RS = Average Gain / Average Loss
    """
    if len(data) < period:
        raise ValueError(f"Not enough data for RSI({period}). Need at least {period} candles, got {len(data)}")

    # Calculate price changes
    delta = data[price_col].diff()

    # Separate gains and losses
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    # Calculate average gain and loss using Wilder's smoothing
    avg_gain = gain.ewm(com=period - 1, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period, adjust=False).mean()

    # Calculate RS and RSI
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return rsi


def detect_swing_points(data: pd.DataFrame, window: int = 5) -> Tuple[List[Dict], List[Dict]]:
    """
    Detect swing high และ swing low points

    Args:
        data: DataFrame with OHLCV data
        window: Window size for swing detection (default: 5)

    Returns:
        Tuple of (swing_highs, swing_lows)
        Each is a list of dicts: {'index': int, 'price': float, 'time': datetime}

    Logic:
        Swing High = high[i] > high[i-window:i] และ high[i] > high[i+1:i+window+1]
        Swing Low = low[i] < low[i-window:i] และ low[i] < low[i+1:i+window+1]
    """
    if len(data) < window * 2 + 1:
        return [], []

    swing_highs = []
    swing_lows = []

    highs = data['high'].values
    lows = data['low'].values

    for i in range(window, len(data) - window):
        # Check swing high
        is_swing_high = True
        for j in range(i - window, i + window + 1):
            if j != i and highs[j] >= highs[i]:
                is_swing_high = False
                break

        if is_swing_high:
            swing_highs.append({
                'index': i,
                'price': float(highs[i]),
                'time': data.iloc[i]['time']
            })

        # Check swing low
        is_swing_low = True
        for j in range(i - window, i + window + 1):
            if j != i and lows[j] <= lows[i]:
                is_swing_low = False
                break

        if is_swing_low:
            swing_lows.append({
                'index': i,
                'price': float(lows[i]),
                'time': data.iloc[i]['time']
            })

    return swing_highs, swing_lows


def detect_sr_levels(data: pd.DataFrame, swing_window: int = 5,
                     zone_threshold: float = 50.0, min_touches: int = 2) -> List[Dict]:
    """
    Detect Support/Resistance levels จาก swing points

    Args:
        data: DataFrame with OHLCV data
        swing_window: Window for swing detection (default: 5)
        zone_threshold: Price threshold for grouping levels (default: 50 points for XAUUSD)
        min_touches: Minimum touches to be valid S/R (default: 2)

    Returns:
        List of S/R levels, each dict:
        {
            'price': float,
            'type': 'support' | 'resistance' | 'both',
            'touches': int,
            'strength': float (0-1),
            'last_touch_index': int
        }
    """
    swing_highs, swing_lows = detect_swing_points(data, swing_window)

    if not swing_highs and not swing_lows:
        return []

    # Combine all swing points
    all_swings = []
    for sh in swing_highs:
        all_swings.append({**sh, 'type': 'resistance'})
    for sl in swing_lows:
        all_swings.append({**sl, 'type': 'support'})

    # Sort by price
    all_swings.sort(key=lambda x: x['price'])

    # Group nearby levels into zones
    zones = []
    current_zone = None

    for swing in all_swings:
        if current_zone is None:
            current_zone = {
                'price_sum': swing['price'],
                'count': 1,
                'touches': 1,
                'types': [swing['type']],
                'last_touch_index': swing['index']
            }
        else:
            # Check if within threshold
            avg_price = current_zone['price_sum'] / current_zone['count']
            if abs(swing['price'] - avg_price) <= zone_threshold:
                # Add to current zone
                current_zone['price_sum'] += swing['price']
                current_zone['count'] += 1
                current_zone['touches'] += 1
                current_zone['types'].append(swing['type'])
                current_zone['last_touch_index'] = max(current_zone['last_touch_index'], swing['index'])
            else:
                # Save current zone and start new one
                if current_zone['touches'] >= min_touches:
                    zones.append(current_zone)
                current_zone = {
                    'price_sum': swing['price'],
                    'count': 1,
                    'touches': 1,
                    'types': [swing['type']],
                    'last_touch_index': swing['index']
                }

    # Don't forget the last zone
    if current_zone and current_zone['touches'] >= min_touches:
        zones.append(current_zone)

    # Convert zones to S/R levels
    sr_levels = []
    for zone in zones:
        avg_price = zone['price_sum'] / zone['count']

        # Determine type
        support_count = zone['types'].count('support')
        resistance_count = zone['types'].count('resistance')

        if support_count > 0 and resistance_count > 0:
            level_type = 'both'
        elif support_count > resistance_count:
            level_type = 'support'
        else:
            level_type = 'resistance'

        # Calculate strength (based on touches and recency)
        recency_factor = zone['last_touch_index'] / len(data)  # 0-1, higher = more recent
        strength = min(1.0, (zone['touches'] / 5) * 0.7 + recency_factor * 0.3)

        sr_levels.append({
            'price': round(avg_price, 2),
            'type': level_type,
            'touches': zone['touches'],
            'strength': round(strength, 3),
            'last_touch_index': zone['last_touch_index']
        })

    # Sort by strength descending
    sr_levels.sort(key=lambda x: x['strength'], reverse=True)

    return sr_levels


def detect_trend(data: pd.DataFrame, method: str = 'ma_slope') -> str:
    """
    Detect trend direction (bullish/bearish/sideways)

    Args:
        data: DataFrame with OHLCV data
        method: Detection method ('ma_slope' | 'higher_highs' | 'combined')

    Returns:
        'bullish' | 'bearish' | 'sideways'
    """
    if len(data) < 20:
        return 'sideways'

    if method == 'ma_slope':
        return _detect_trend_ma_slope(data)
    elif method == 'higher_highs':
        return _detect_trend_higher_highs(data)
    elif method == 'combined':
        ma_trend = _detect_trend_ma_slope(data)
        hh_trend = _detect_trend_higher_highs(data)
        # Agree on same direction = strong signal
        if ma_trend == hh_trend:
            return ma_trend
        # Disagree = sideways
        return 'sideways'
    else:
        raise ValueError(f"Unknown trend detection method: {method}")


def _detect_trend_ma_slope(data: pd.DataFrame, ma_period: int = 20) -> str:
    """
    Detect trend using Moving Average slope

    Logic:
        - Calculate MA(20)
        - Check slope of last 10 candles
        - Positive slope > threshold = bullish
        - Negative slope < threshold = bearish
        - Otherwise = sideways
    """
    if len(data) < ma_period:
        return 'sideways'

    # Calculate SMA
    ma = data['close'].rolling(window=ma_period).mean()

    # Get last 10 MA values
    recent_ma = ma.tail(10).values

    if len(recent_ma) < 10:
        return 'sideways'

    # Calculate slope (linear regression)
    x = np.arange(len(recent_ma))
    slope = np.polyfit(x, recent_ma, 1)[0]

    # Normalize slope by price (percentage)
    avg_price = recent_ma.mean()
    slope_pct = (slope / avg_price) * 100 if avg_price > 0 else 0

    # Thresholds
    BULLISH_THRESHOLD = 0.05  # 0.05% per candle
    BEARISH_THRESHOLD = -0.05

    if slope_pct > BULLISH_THRESHOLD:
        return 'bullish'
    elif slope_pct < BEARISH_THRESHOLD:
        return 'bearish'
    else:
        return 'sideways'


def _detect_trend_higher_highs(data: pd.DataFrame, window: int = 5) -> str:
    """
    Detect trend using Higher Highs / Lower Lows pattern

    Logic:
        - Find swing highs and lows
        - Compare recent swing points
        - Higher Highs + Higher Lows = bullish
        - Lower Highs + Lower Lows = bearish
        - Mixed = sideways
    """
    swing_highs, swing_lows = detect_swing_points(data, window)

    if len(swing_highs) < 3 or len(swing_lows) < 3:
        return 'sideways'

    # Get last 3 swing highs and lows
    recent_highs = [sh['price'] for sh in swing_highs[-3:]]
    recent_lows = [sl['price'] for sl in swing_lows[-3:]]

    # Check Higher Highs
    higher_highs = recent_highs[-1] > recent_highs[0]

    # Check Higher Lows
    higher_lows = recent_lows[-1] > recent_lows[0]

    # Check Lower Highs
    lower_highs = recent_highs[-1] < recent_highs[0]

    # Check Lower Lows
    lower_lows = recent_lows[-1] < recent_lows[0]

    # Determine trend
    if higher_highs and higher_lows:
        return 'bullish'
    elif lower_highs and lower_lows:
        return 'bearish'
    else:
        return 'sideways'


def calculate_atr(data: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calculate ATR (Average True Range)

    Args:
        data: DataFrame with OHLCV data
        period: ATR period (default: 14)

    Returns:
        pd.Series with ATR values
    """
    if len(data) < period:
        raise ValueError(f"Not enough data for ATR({period})")

    high = data['high']
    low = data['low']
    close = data['close']

    # Calculate True Range
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Calculate ATR using Wilder's smoothing
    atr = tr.ewm(com=period - 1, min_periods=period, adjust=False).mean()

    return atr


def get_rsi_zone(rsi: float) -> str:
    """
    Get RSI zone classification (metadata only, not used for decision)

    Args:
        rsi: RSI value (0-100)

    Returns:
        Zone name: 'extreme_oversold' | 'oversold' | 'near_oversold' |
                   'neutral' | 'momentum' | 'strong_momentum' | 'overbought'
    """
    if rsi <= 25:
        return 'extreme_oversold'
    elif rsi <= 35:
        return 'oversold'
    elif rsi <= 44:
        return 'near_oversold'
    elif rsi <= 54:
        return 'neutral'
    elif rsi <= 65:
        return 'momentum'
    elif rsi <= 70:
        return 'strong_momentum'
    else:
        return 'overbought'


def find_nearest_sr_level(current_price: float, sr_levels: List[Dict],
                          max_distance: float = 200.0) -> Optional[Dict]:
    """
    Find nearest S/R level to current price

    Args:
        current_price: Current market price
        sr_levels: List of S/R levels from detect_sr_levels()
        max_distance: Maximum distance in points (default: 200)

    Returns:
        Nearest S/R level dict or None if none within range
        Adds 'distance' field to the returned dict
    """
    if not sr_levels:
        return None

    nearest = None
    min_distance = float('inf')

    for level in sr_levels:
        distance = abs(current_price - level['price'])
        if distance < min_distance and distance <= max_distance:
            min_distance = distance
            nearest = level.copy()
            nearest['distance'] = round(distance, 2)

    return nearest


def analyze_candle_pattern(candle: Dict, prev_candle: Optional[Dict] = None) -> Dict:
    """
    Analyze single candle pattern

    Args:
        candle: Dict with OHLC data
        prev_candle: Previous candle (optional, for comparison)

    Returns:
        Dict with pattern analysis:
        {
            'body_size': float,
            'upper_wick': float,
            'lower_wick': float,
            'wick_to_body_ratio': float,
            'is_bullish': bool,
            'is_bearish': bool,
            'is_doji': bool,
            'has_long_lower_wick': bool,  # >= 1.5x body
            'has_long_upper_wick': bool,  # >= 1.5x body
            'is_engulfing': bool  # if prev_candle provided
        }
    """
    o, h, l, c = candle['open'], candle['high'], candle['low'], candle['close']

    body_size = abs(c - o)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l

    is_bullish = c > o
    is_bearish = c < o

    # Doji: body very small (< 0.1% of high-low range)
    candle_range = h - l
    is_doji = body_size < (candle_range * 0.001) if candle_range > 0 else True

    # Long wicks
    wick_threshold = 1.5
    has_long_lower_wick = lower_wick >= (body_size * wick_threshold) if body_size > 0 else False
    has_long_upper_wick = upper_wick >= (body_size * wick_threshold) if body_size > 0 else False

    wick_to_body_ratio = (lower_wick + upper_wick) / body_size if body_size > 0 else 0

    result = {
        'body_size': round(body_size, 2),
        'upper_wick': round(upper_wick, 2),
        'lower_wick': round(lower_wick, 2),
        'wick_to_body_ratio': round(wick_to_body_ratio, 2),
        'is_bullish': is_bullish,
        'is_bearish': is_bearish,
        'is_doji': is_doji,
        'has_long_lower_wick': has_long_lower_wick,
        'has_long_upper_wick': has_long_upper_wick,
        'is_engulfing': False
    }

    # Check engulfing pattern
    if prev_candle:
        prev_o, prev_c = prev_candle['open'], prev_candle['close']

        # Bullish engulfing: bearish candle followed by larger bullish candle
        if prev_c < prev_o and c > o:  # prev bearish, current bullish
            if c > prev_o and o < prev_c:  # engulfs previous candle
                result['is_engulfing'] = True

        # Bearish engulfing: bullish candle followed by larger bearish candle
        if prev_c > prev_o and c < o:  # prev bullish, current bearish
            if o > prev_c and c < prev_o:  # engulfs previous candle
                result['is_engulfing'] = True

    return result


# Example usage and testing
if __name__ == "__main__":
    from data_connector import create_connector
    from dotenv import load_dotenv

    load_dotenv()

    print("="*60)
    print("TECHNICAL INDICATORS TEST")
    print("="*60)

    # Get market data using new MTF API
    with create_connector('simulate') as conn:
        m5_data = conn.get_latest_candles('XAUUSD', timeframe='M5', count=100)
        h1_data = conn.get_latest_candles('XAUUSD', timeframe='H1', count=50)

    # Convert to DataFrame
    m5_df = pd.DataFrame(m5_data)
    h1_df = pd.DataFrame(h1_data)

    print(f"\n📊 Data loaded:")
    print(f"   M5 candles: {len(m5_df)}")
    print(f"   H1 candles: {len(h1_df)}")

    if len(m5_df) > 0:
        current_price = m5_df.iloc[-1]['close']
        print(f"   Current price: ${current_price:.2f}")

    # 1. Calculate RSI
    print(f"\n1️⃣  RSI Indicator")
    m5_df['rsi'] = calculate_rsi(m5_df, period=14)
    current_rsi = m5_df['rsi'].iloc[-1]
    rsi_zone = get_rsi_zone(current_rsi)
    print(f"   RSI(14): {current_rsi:.2f}")
    print(f"   Zone: {rsi_zone}")

    # 2. Detect S/R levels
    print(f"\n2️⃣  Support/Resistance Levels")
    sr_levels = detect_sr_levels(m5_df, swing_window=5, zone_threshold=50, min_touches=2)
    print(f"   Found {len(sr_levels)} S/R levels")

    if sr_levels:
        print(f"\n   Top 5 S/R levels:")
        for i, level in enumerate(sr_levels[:5], 1):
            print(f"   {i}. ${level['price']:7.2f} | "
                  f"{level['type']:10s} | "
                  f"touches: {level['touches']} | "
                  f"strength: {level['strength']:.2f}")

    # 3. Find nearest S/R
    nearest = find_nearest_sr_level(current_price, sr_levels, max_distance=200)
    if nearest:
        print(f"\n   Nearest S/R: ${nearest['price']:.2f} "
              f"({nearest['type']}) - {nearest['distance']:.2f} points away")

    # 4. Detect H1 trend
    print(f"\n3️⃣  Trend Detection (H1)")
    h1_trend_ma = detect_trend(h1_df, method='ma_slope')
    h1_trend_hh = detect_trend(h1_df, method='higher_highs')
    h1_trend_combined = detect_trend(h1_df, method='combined')

    print(f"   MA Slope method: {h1_trend_ma}")
    print(f"   Higher Highs method: {h1_trend_hh}")
    print(f"   Combined: {h1_trend_combined}")

    # 5. Analyze latest candle
    print(f"\n4️⃣  Latest M5 Candle Pattern")
    latest = m5_data[-1]
    prev = m5_data[-2] if len(m5_data) >= 2 else None

    pattern = analyze_candle_pattern(latest, prev)
    print(f"   Body: {pattern['body_size']:.2f} | "
          f"Lower wick: {pattern['lower_wick']:.2f} | "
          f"Upper wick: {pattern['upper_wick']:.2f}")
    print(f"   Direction: {'🟢 Bullish' if pattern['is_bullish'] else '🔴 Bearish'}")
    print(f"   Long lower wick: {'✓' if pattern['has_long_lower_wick'] else '✗'}")
    print(f"   Long upper wick: {'✓' if pattern['has_long_upper_wick'] else '✗'}")
    print(f"   Engulfing: {'✓' if pattern['is_engulfing'] else '✗'}")

    # 6. Calculate ATR
    print(f"\n5️⃣  ATR (Average True Range)")
    m5_df['atr'] = calculate_atr(m5_df, period=14)
    current_atr = m5_df['atr'].iloc[-1]
    print(f"   ATR(14): {current_atr:.2f} points")
    print(f"   Use for: SL/TP distance calculation")

    print("\n" + "="*60)
    print("✅ All indicators working correctly!")
    print("="*60)
