"""
Signal Engine Wrapper — v2.1
Integrates xauusd_signal.py as the main Signal Engine (replaces G1 pattern detection)

Changes:
- G1 (pattern_detector.py) → Signal Engine (xauusd_signal.py)
- Claude API role: Decision maker → Reviewer only
- Mountain state tracking for round 2 detection
- Single TF mode: M5 only
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime

from utils.xauusd_signal import find_signal, OHLC, Signal, format_signal

logger = logging.getLogger(__name__)


def convert_candles_to_ohlc(candles: List[dict]) -> List[OHLC]:
    """
    Convert existing candle dict format to OHLC format

    Args:
        candles: List of candle dicts with keys: 'time', 'open', 'high', 'low', 'close', 'timestamp'

    Returns:
        List of OHLC objects
    """
    ohlc_bars = []
    for i, candle in enumerate(candles):
        # Get timestamp string (prefer 'timestamp' field, fallback to 'time')
        timestamp = candle.get('timestamp', candle.get('time'))
        if isinstance(timestamp, datetime):
            time_str = timestamp.isoformat()
        else:
            time_str = str(timestamp)

        ohlc = OHLC(
            time=time_str,
            open=candle['open'],
            high=candle['high'],
            low=candle['low'],
            close=candle['close'],
            bar_num=i + 1
        )
        ohlc_bars.append(ohlc)

    return ohlc_bars


def run_signal_engine(
    candles_by_tf: Dict[str, List[dict]],
    portfolio: float,
    mountain_state: Optional[dict] = None
) -> dict:
    """
    Run Signal Engine (replaces G1 pattern detection)

    Args:
        candles_by_tf: Dict of candles by timeframe (e.g., {'M5': [candle1, candle2, ...]})
        portfolio: Current portfolio balance (USD)
        mountain_state: Mountain state for round 2 detection (from portfolio_state)

    Returns:
        world_state dict compatible with G2/G3 pipeline:
        {
            'selected_tf': 'M5',
            'chart_type': 'DOWNTREND' | 'UPTREND' | 'MOUNTAIN' | 'MOUNTAIN_R2' | 'unclear',
            'quality': float,
            'chart_detail': dict,
            'technique_candidate': str,
            'range': dict,
            'signal': Signal | None,
            'current_price': float,
            'session': str,
            'metadata': dict,
            'mountain_state': dict (updated)
        }
    """
    # Single TF mode: Use M5 only
    timeframe = 'M5'
    candles = candles_by_tf.get(timeframe, [])

    if not candles or len(candles) < 55:
        logger.warning(f"Not enough M5 candles: {len(candles)} < 55")
        return {
            'selected_tf': timeframe,
            'chart_type': 'unclear',
            'quality': 0.0,
            'signal': None,
            'skip_reason': 'insufficient_data'
        }

    # Convert to OHLC format
    ohlc_bars = convert_candles_to_ohlc(candles)
    logger.debug(f"Converted {len(ohlc_bars)} M5 candles to OHLC format")

    # Call xauusd_signal.find_signal()
    signal = find_signal(
        bars=ohlc_bars,
        portfolio=portfolio,
        mountain_state=mountain_state
    )

    # Get current price and session
    current_price = candles[-1]['close']
    timestamp = candles[-1].get('timestamp', datetime.now())
    session = detect_session(timestamp)

    # Calculate range
    highs = [c['high'] for c in candles]
    lows = [c['low'] for c in candles]
    range_high = max(highs)
    range_low = min(lows)
    range_usd = range_high - range_low
    range_pip = range_usd * 100

    if signal is None:
        # No signal found
        logger.info("Signal Engine: No setup found")
        return {
            'selected_tf': timeframe,
            'chart_type': 'unclear',
            'quality': 0.0,
            'chart_detail': {},
            'technique_candidate': 'skip',
            'range': {
                'high': range_high,
                'low': range_low,
                'usd': range_usd,
                'pip': range_pip
            },
            'signal': None,
            'current_price': current_price,
            'session': session,
            'ohlc_last_10': candles[-10:],
            'metadata': {
                'candles_checked': len(candles),
                'range_55': round(range_usd, 2)
            },
            'mountain_state': mountain_state  # Return unchanged
        }

    # Signal found — convert to world_state format
    logger.info(f"Signal Engine: {signal.pattern} {signal.direction} "
                f"(quality={signal.quality}, R:R={signal.rr:.2f})")

    # Map pattern to chart_type
    chart_type_mapping = {
        'DOWNTREND': 'downtrend',
        'UPTREND': 'uptrend',
        'MOUNTAIN': 'mountain',
        'MOUNTAIN_R2': 'mountain_r2'
    }
    chart_type = chart_type_mapping.get(signal.pattern, 'unclear')

    # Map quality string to numeric (100%✓ → 1.0, ~60%⚠️ → 0.6)
    quality_mapping = {
        '100%✓': 1.0,
        '~60%⚠️': 0.6,
        '✗': 0.0
    }
    quality = quality_mapping.get(signal.quality, 0.5)

    # Determine technique based on pattern
    # Signal Engine always provides Entry/SL/TP, so technique is based on pattern type
    if signal.pattern in ['DOWNTREND', 'UPTREND']:
        # Check if it's twin candle or breakout based on signal details
        # For now, default to twin_candle (xauusd_signal focuses on twin candle setups)
        technique = signal.details.get('technique', 'twin_candle')
    elif signal.pattern in ['MOUNTAIN', 'MOUNTAIN_R2']:
        technique = 'mountain'
    else:
        technique = 'skip'

    # Build chart_detail from signal
    chart_detail = {
        'pattern': signal.pattern,
        'direction': signal.direction,
        'quality_str': signal.quality,
        'entry': signal.entry,
        'sl': signal.sl,
        'sl_name': signal.sl_name,
        'tp_order': signal.tp_order,
        'tp_ref': signal.tp_ref,
        'tp_name': signal.tp_name,
        'rr': signal.rr,
        'risk_pip': signal.risk_pip,
        'reward_pip': signal.reward_pip,
        'lot': signal.lot,
        'R55': signal.R55,
        'details': signal.details
    }

    # TODO: Mountain state tracking needs proper implementation
    # xauusd_signal.py expects: {'prev_entry', 'prev_entry_bar', 'base_lo_r1', 'tp_bar'}
    # For Phase 1, disable mountain state tracking
    updated_mountain_state = None

    if signal.pattern == 'MOUNTAIN':
        logger.info("Mountain Round 1 detected (state tracking disabled in Phase 1)")
    elif signal.pattern == 'MOUNTAIN_R2':
        logger.info("Mountain Round 2 detected (state tracking disabled in Phase 1)")

    # Build world_state
    world_state = {
        'selected_tf': timeframe,
        'chart_type': chart_type,
        'quality': quality,
        'chart_detail': chart_detail,
        'technique_candidate': technique,
        'range': {
            'high': range_high,
            'low': range_low,
            'usd': range_usd,
            'pip': range_pip
        },
        'signal': signal,  # Include full Signal object for G2/G3 to use
        'current_price': current_price,
        'session': session,
        'ohlc_last_10': candles[-10:],
        'metadata': {
            'candles_checked': len(candles),
            'range_55': round(range_usd, 2),
            'signal_engine_version': '4.20'
        },
        'mountain_state': updated_mountain_state  # Return updated state
    }

    return world_state


def detect_session(timestamp: datetime) -> str:
    """
    Detect trading session from timestamp

    Args:
        timestamp: Candle timestamp

    Returns:
        'asia' | 'london' | 'us' | 'us_close' | 'unknown'
    """
    if not isinstance(timestamp, datetime):
        return 'unknown'

    hour = timestamp.hour

    # Asia: 00:00 - 08:00 UTC
    if 0 <= hour < 8:
        return 'asia'
    # London: 08:00 - 12:00 UTC
    elif 8 <= hour < 12:
        return 'london'
    # US: 12:00 - 20:00 UTC
    elif 12 <= hour < 20:
        return 'us'
    # US Close: 20:00 - 00:00 UTC
    elif 20 <= hour < 24:
        return 'us_close'
    else:
        return 'unknown'
