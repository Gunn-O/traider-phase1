"""
Signal Engine Wrapper

Active strategies (per config/strategies.json + 3 reference notebooks under strategy/):
  - MOUNTAIN              (notebook v4.61 — strategies/mountain.py)
  - MAI_RUAY              (Father/Mother — strategies/mai_ruay.py)
  - UPTREND_SCANNER       (notebook v3.8 — strategies/uptrend_downtrend_scanner.py)
  - DOWNTREND_SCANNER     (notebook v3.8 — strategies/uptrend_downtrend_scanner.py)

Each strategy runs independently on M5 bars; signal_engine picks the best by R:R.
Time filter: block trades 60min before market close (21:00 UTC).
Gap filter: wait 80 bars after opening gap > 20% R55.
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime
import pytz

from utils.xauusd_signal import find_signal, OHLC, Signal, format_signal

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# V4.25 Filters
# ═══════════════════════════════════════════════════════════════════

def is_near_market_close(candle_time: datetime,
                        close_hour: int = 21,
                        close_minute: int = 0,
                        buffer_minutes: int = 120) -> bool:
    """
    V4.25: Block trades before market close

    Args:
        candle_time: Current candle timestamp
        close_hour: Market close hour in UTC (default 21)
        close_minute: Market close minute (default 0)
        buffer_minutes: Minutes before close to block (default 60)

    Returns:
        True if within buffer zone (block trading), False otherwise
    """
    # Convert to UTC if not already
    if candle_time.tzinfo is None:
        utc_time = pytz.UTC.localize(candle_time)
    else:
        utc_time = candle_time.astimezone(pytz.UTC)

    # V65: Only block on Friday (weekday 4)
    if utc_time.weekday() != 4:
        return False

    # Check if in 19:00-21:00 UTC range (120min before 21:00 close)
    hour = utc_time.hour
    minute = utc_time.minute

    # With 120min buffer: block from 19:00-21:00
    # If hour is 19 or 20, block
    if hour in [close_hour - 2, close_hour - 1]:
        return True

    # If exactly at close hour and within first few minutes
    if hour == close_hour and minute <= close_minute:
        return True

    return False


def check_opening_gap(candles: List[dict], R55: float,
                     gap_threshold_pct: float = 0.20) -> bool:
    """
    V4.25: Check for opening gap

    Args:
        candles: List of candles
        R55: Range 55 (pip)
        gap_threshold_pct: Gap threshold as % of R55 (default 20%)

    Returns:
        True if there's a gap > threshold (should skip), False otherwise

    Note: This checks if the MOST RECENT gap (last 2 candles) is large.
          For backtest initialization, use a separate function to find
          the gap bar index and start from there.
    """
    if len(candles) < 2:
        return False

    # Check gap between last 2 candles
    prev_candle = candles[-2]
    curr_candle = candles[-1]

    # Gap = abs(current open - previous close)
    gap = abs(curr_candle['open'] - prev_candle['close']) * 100  # in pip

    gap_threshold = R55 * gap_threshold_pct

    if gap > gap_threshold:
        logger.info(f"Opening gap detected: {gap:.0f}pip > {gap_threshold:.0f}pip ({gap_threshold_pct*100:.0f}%R55)")
        return True

    return False


def _parse_quality(quality_str: str) -> float:
    """
    แปลง quality string จาก xauusd_signal.py → float

    xauusd_signal.py ส่ง:
      DOWNTREND/UPTREND: "100%✓" หรือ "~60%⚠️" หรือ "✗"
      MOUNTAIN:          "✅"     หรือ "⚠️ นาน"

    Note: ใช้ทั้ง ✓ (U+2713) และ ✅ (U+2705) เพราะ xauusd_signal.py ใช้ ✓

    G2 threshold: quality >= 0.50
    """
    # 100% quality (รองรับทั้ง ✓ และ ✅)
    if quality_str in ("100%✓", "100%✅", "✓", "✅"):
        return 1.0   # ผ่าน G2 (≥ 0.50)
    # ~60% quality (รองรับทั้ง ⚠ และ ⚠️)
    elif quality_str in ("~60%⚠️", "~60%⚠"):
        return 0.6   # ผ่าน G2 (≥ 0.50)
    # Mountain นานเกิน 40 แท่ง
    elif quality_str in ("⚠️ นาน", "⚠ นาน"):
        return 0.4   # ไม่ผ่าน G2 (< 0.50) — ภูเขานานเกิน 40 แท่ง
    else:
        # "✗" หรือ "❌" หรือ unknown
        return 0.0   # ไม่ผ่าน G2


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
    mountain_state: Optional[dict] = None,
    scanner_state: Optional[dict] = None,
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
            'chart_type': 'mountain' | 'mai_ruay' | 'uptrend' | 'downtrend' | 'unclear',
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
    # Active timeframe — config-driven (default M5, override via env BACKTEST_TIMEFRAME)
    import os as _os
    timeframe = _os.getenv('BACKTEST_TIMEFRAME', 'M5').upper()
    candles = candles_by_tf.get(timeframe, [])
    # Fallback to first available TF if exact match not found
    if not candles:
        for tf in ('M1', 'M5', 'M15', 'M30', 'H1', 'H4'):
            if candles_by_tf.get(tf):
                timeframe = tf
                candles = candles_by_tf[tf]
                break

    if not candles or len(candles) < 55:
        logger.warning(f"Not enough {timeframe} candles: {len(candles)} < 55")
        return {
            'selected_tf': timeframe,
            'chart_type': 'unclear',
            'quality': 0.0,
            'signal': None,
            'skip_reason': 'insufficient_data'
        }

    # V4.25: Time filter — Block trades near market close
    current_timestamp = candles[-1].get('timestamp', datetime.now())
    if is_near_market_close(current_timestamp):
        logger.info("V4.25 Time filter: Near market close (< 60min before 21:00 UTC) — SKIP")
        return {
            'selected_tf': timeframe,
            'chart_type': 'unclear',
            'quality': 0.0,
            'signal': None,
            'skip_reason': 'near_market_close'
        }

    # Convert to OHLC format
    ohlc_bars = convert_candles_to_ohlc(candles)
    logger.debug(f"Converted {len(ohlc_bars)} M5 candles to OHLC format")

    # Run each enabled strategy and collect candidates.
    # is_pattern_active_for_tf() reads config/strategies.json so toggles take
    # effect on the next cycle without restart. The current TF comes from the
    # subprocess env var the api_server sets when spawning each bot.
    import os as _os
    from utils.strategy_loader import is_pattern_active_for_tf
    from strategies import mountain as _mountain_strat
    from strategies import mai_ruay as _mai_ruay_strat

    current_tf = _os.getenv("BACKTEST_TIMEFRAME", "M5").upper()

    candidates: list = []

    # Tier 2: each strategy writes its skip reason into a per-strategy debug
    # dict, surfaced in world_state['skip_reasons']. UI shows them in the Live
    # Snapshot panel so the user knows WHY no signal fired this cycle.
    skip_reasons: dict = {}

    # MOUNTAIN — Mountain Round 1 (notebook v4.61). MOUNTAIN_R2 deprecated.
    if is_pattern_active_for_tf('MOUNTAIN', current_tf):
        _dbg_mtn: dict = {}
        sig_mtn = _mountain_strat.find_signal(
            bars=ohlc_bars, portfolio=portfolio, mountain_state=mountain_state, debug=_dbg_mtn
        )
        if sig_mtn is not None and sig_mtn.pattern == 'MOUNTAIN':
            candidates.append(sig_mtn)
        elif _dbg_mtn.get('skip'):
            skip_reasons['MOUNTAIN'] = _dbg_mtn['skip']

    # MAI_RUAY — Father/Mother candle (notebook engine 1-8 / 60-100% / 4-30%)
    if is_pattern_active_for_tf('MAI_RUAY', current_tf):
        _dbg_mr: dict = {}
        sig_mr = _mai_ruay_strat.find_signal(bars=ohlc_bars, portfolio=portfolio, debug=_dbg_mr)
        if sig_mr is not None:
            candidates.append(sig_mr)
        elif _dbg_mr.get('skip'):
            skip_reasons['MAI_RUAY'] = _dbg_mr['skip']

    # UPTREND_SCANNER / DOWNTREND_SCANNER (notebook v3.8) — wrapper picks BUY
    # first, falls back to SELL. Each variant gated by its own (pattern, TF) flag.
    # `scanner_state` is loaded from portfolio_state_cache by the caller; the
    # detector mutates it in place (updates current segment_id; consults
    # stopped_*_segments to refuse re-entry on segments that already had a LOSS).
    updated_scanner_state = scanner_state
    if (is_pattern_active_for_tf('UPTREND_SCANNER', current_tf)
            or is_pattern_active_for_tf('DOWNTREND_SCANNER', current_tf)):
        from strategies import uptrend_downtrend_scanner as _ud_scanner
        from utils.xauusd_signal import ScannerSegmentState
        _scan_state_obj = ScannerSegmentState.from_dict(scanner_state)
        _dbg_ud: dict = {'buy': {}, 'sell': {}}
        sig_ud = _ud_scanner.find_signal(
            bars=ohlc_bars, portfolio=portfolio, debug=_dbg_ud, state=_scan_state_obj
        )
        updated_scanner_state = _scan_state_obj.to_dict()
        if sig_ud is not None and is_pattern_active_for_tf(sig_ud.pattern, current_tf):
            candidates.append(sig_ud)
        else:
            if _dbg_ud['buy'].get('skip'):
                skip_reasons['UPTREND_SCANNER'] = _dbg_ud['buy']['skip']
            if _dbg_ud['sell'].get('skip'):
                skip_reasons['DOWNTREND_SCANNER'] = _dbg_ud['sell']['skip']

    # Pick best by R:R (matches existing xauusd_signal selection logic)
    signal = max(candidates, key=lambda s: s.rr) if candidates else None

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
            'mountain_state': mountain_state,  # Return unchanged
            'scanner_state': updated_scanner_state,  # v3.8 segment tracking
            'skip_reasons': skip_reasons,       # Tier 2: per-strategy SKIP reasons
        }

    # Signal found — convert to world_state format
    logger.info(f"Signal Engine: {signal.pattern} {signal.direction} "
                f"(quality={signal.quality}, R:R={signal.rr:.2f})")

    # Map pattern to chart_type — only the 3 active strategies
    chart_type_mapping = {
        'MOUNTAIN': 'mountain',
        'MAI_RUAY': 'mai_ruay',             # Branch F (Father/Mother candle)
        'UPTREND_SCANNER': 'uptrend',       # v3.8 scanner (BUY)
        'DOWNTREND_SCANNER': 'downtrend',   # v3.8 scanner (SELL)
    }
    chart_type = chart_type_mapping.get(signal.pattern, 'unclear')

    # Parse quality string from xauusd_signal.py
    quality = _parse_quality(signal.quality)

    # Determine technique based on pattern
    if signal.pattern == 'MOUNTAIN':
        technique = 'mountain'
    elif signal.pattern == 'MAI_RUAY':
        technique = 'mai_ruay'
    elif signal.pattern in ['UPTREND_SCANNER', 'DOWNTREND_SCANNER']:
        technique = 'scanner_v34'
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
            'signal_engine_version': '4.25'
        },
        'mountain_state': updated_mountain_state,  # Return updated state
        'scanner_state': updated_scanner_state,    # v3.8 segment tracking
        'skip_reasons': skip_reasons,                # Tier 2: SKIPs from non-firing strategies
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
