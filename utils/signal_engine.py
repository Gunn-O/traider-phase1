"""
Signal Engine Wrapper

Active strategies (per config/strategies.json + 3 reference notebooks under strategy/):
  - MOUNTAIN              (notebook v4.61 — strategies/mountain.py)
  - MAI_RUAY              (Father/Mother — strategies/mai_ruay.py)
  - UPTREND_SCANNER       (notebook v4.2 — strategies/uptrend_downtrend_scanner.py)
  - DOWNTREND_SCANNER     (notebook v4.2 — strategies/uptrend_downtrend_scanner.py)

Each strategy runs independently on M5 bars; signal_engine picks the best by R:R.
Time filter: block trades 60min before market close (21:00 UTC).
Gap filter: wait 80 bars after opening gap > 20% R55.
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime, timezone
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
    V4.25: Block trades within `buffer_minutes` of Friday's market close.

    Args:
        candle_time: Current candle timestamp. Aware datetime is converted
                     to UTC; naive datetime is INTERPRETED AS SYSTEM LOCAL
                     and converted (prior version mislabeled naive as UTC
                     which shifted the block window by the system offset —
                     e.g. on a Bangkok PC, "21:00 UTC close" was firing at
                     14:00 UTC because the BKK wall-clock said 21:00).
        close_hour: Market close hour IN UTC (default 21)
        close_minute: Market close minute (default 0)
        buffer_minutes: Minutes before close to block (default 120 = 2h)

    Returns:
        True if within buffer zone (block trading), False otherwise
    """
    if candle_time.tzinfo is None:
        # Interpret naive as local wall-clock, convert to UTC. .astimezone()
        # on a naive datetime treats it as system local per stdlib.
        utc_time = candle_time.astimezone(timezone.utc)
    else:
        utc_time = candle_time.astimezone(timezone.utc)

    # V65: Only block on Friday (weekday 4)
    if utc_time.weekday() != 4:
        return False

    # Compute the close moment and the block-window start
    from datetime import timedelta as _td
    close_at = utc_time.replace(hour=close_hour, minute=close_minute,
                                second=0, microsecond=0)
    block_from = close_at - _td(minutes=buffer_minutes)
    # Block window is [block_from, close_at]; the original hour-based check
    # didn't handle non-zero buffer_minutes or close_minute correctly.
    return block_from <= utc_time <= close_at


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
    mai_ruay_state: Optional[dict] = None,
) -> dict:
    """
    Run Signal Engine (replaces G1 pattern detection)

    Args:
        candles_by_tf: Dict of candles by timeframe (e.g., {'M5': [candle1, candle2, ...]})
        portfolio: Current portfolio balance (USD)
        mountain_state: Mountain state for round 2 detection (from portfolio_state)
        mai_ruay_state: MaiRuay v2 state — carries r1_info after a SL for R2 retry
                        {'r1_info': {'tech', 'f_open_r1', 'entry_bar', 'direction'}, 'r1_bar_idx': int}

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
            'mountain_state': dict (updated),
            'mai_ruay_state': dict (updated — r1_info cleared on R2 hit or stale)
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

    # V4.25: Time filter — Block trades near Friday market close.
    # Read close_hour + buffer from config so toggling the JSON takes effect
    # on the next cycle (no restart).
    #
    # IMPORTANT — use REAL `datetime.now(UTC)`, not the candle timestamp:
    # during weekend the market is closed and MT5 returns STALE Friday-near-
    # close candles. Using candle time made the filter trip continuously
    # through Saturday-Sunday (and bleed into Monday morning until fresh
    # candles arrived) because Friday near-close timestamps kept satisfying
    # the window. Real wall-clock UTC is what "near close" actually means.
    # Backtest mode still passes candle time via current_timestamp through
    # is_backtest detection below.
    current_timestamp = candles[-1].get('timestamp', datetime.now())
    try:
        from utils.strategy_loader import load_config as _load_cfg
        _tf_cfg = (_load_cfg().get('global_settings', {}).get('time_filter') or {})
    except Exception:
        _tf_cfg = {}
    _close_h   = int(_tf_cfg.get('close_hour_utc', 21))
    _close_min = int(_tf_cfg.get('close_minute_utc', 0))
    _buf_min   = int(_tf_cfg.get('buffer_minutes', 120))
    _filter_on = bool(_tf_cfg.get('enabled', True))
    # Detect backtest by env var (set by main.py when --backtest is active)
    # vs. live cycle. In live we want clock-time semantics; in backtest the
    # candle IS the clock as far as the strategy is concerned.
    import os as _os_for_filter
    _is_backtest_mode = bool(_os_for_filter.getenv('TRAIDER_BACKTEST_ACTIVE'))
    _filter_time = current_timestamp if _is_backtest_mode else datetime.now(timezone.utc)
    if _filter_on and is_near_market_close(
        _filter_time,
        close_hour=_close_h,
        close_minute=_close_min,
        buffer_minutes=_buf_min,
    ):
        logger.info(
            f"V4.25 Time filter: within {_buf_min}min of "
            f"{_close_h:02d}:{_close_min:02d} UTC Friday close — SKIP "
            f"(check_time={_filter_time.isoformat() if hasattr(_filter_time, 'isoformat') else _filter_time})"
        )
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
    # MaiRuay v2.04 (notebook Mairuay_Basic_Father_V2.04_M1) — multi-entry +
    # Round 2 via mai_ruay_state['r1_info'].
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

    # MAI_RUAY v2.04 — Father/Mother candle with multi-entry + Round 2
    #   notebook: strategy/Mairuay_Basic_Father_V2.04_M1.md
    #   engine:   strategies/mai_ruay.py
    updated_mai_ruay_state = dict(mai_ruay_state) if mai_ruay_state else {}
    if is_pattern_active_for_tf('MAI_RUAY', current_tf):
        # Tick the R2 countdown every cycle the engine runs (regardless of
        # whether R1 fires). We use bars_elapsed (incremented per cycle) rather
        # than (len(bars)-curr_bar) because main.py passes a SLIDE WINDOW to
        # signal_engine — len(bars)-1 is always ~RANGE_WINDOW-1, so positional
        # math vs the R1 entry bar is meaningless. The counter is the only
        # cycle-accurate clock available to us.
        _r1 = updated_mai_ruay_state.get('r1_info')
        if _r1 is not None:
            updated_mai_ruay_state['r1_bars_elapsed'] = updated_mai_ruay_state.get('r1_bars_elapsed', 0) + 1
            if updated_mai_ruay_state['r1_bars_elapsed'] > 16:
                logger.info(
                    f"MaiRuay v2 r1_info expired (bars_elapsed="
                    f"{updated_mai_ruay_state['r1_bars_elapsed']} > 16) → drop"
                )
                updated_mai_ruay_state.pop('r1_info', None)
                updated_mai_ruay_state.pop('r1_bars_elapsed', None)
                _r1 = None

        # ── Live mode: append a SYNTHETIC CHILD bar ────────────────────────
        # Notebook spec: in `analyze_bar`, `child = bars[bar_idx]` and entry =
        # `child.open` (= the moment mother closed). In a backtest loop this
        # bar already exists in df. In live, the bot wakes ~2s after mother
        # close — the new bar (child) has JUST started and its only known
        # price point is "current market" ≈ mother.close.
        #
        # If we skip this synthesis, `bars[-1]` is the bar that just closed,
        # the engine treats THAT as the child, and `child.open` ends up being
        # GRANDMOTHER's close — entry shifts back by 1 candle (the delay the
        # user saw on the chart). Appending a synthetic child fixes the lag
        # without changing any analyzer logic.
        #
        # Backtest path is unchanged. Mountain + Scanner use the original
        # `ohlc_bars` below — no behavior change there.
        _bars_for_mr = ohlc_bars
        _synth_time: Optional[str] = None  # set when synthetic is in use
        if not _is_backtest_mode and ohlc_bars:
            _last = ohlc_bars[-1]
            _tf_sec_map = {'M1': 60, 'M5': 300, 'M15': 900,
                           'M30': 1800, 'H1': 3600, 'H4': 14400}
            _tf_sec = _tf_sec_map.get(current_tf, 60)
            try:
                from datetime import timedelta as _td_synth
                from dateutil import parser as _dtp_synth
                _last_dt = _dtp_synth.parse(str(_last.time))
                _next_time = (_last_dt + _td_synth(seconds=_tf_sec)).isoformat()
            except Exception:
                _next_time = str(_last.time)
            _synth_child = OHLC(
                time=_next_time,
                open=_last.close,
                high=_last.close,
                low=_last.close,
                close=_last.close,
                bar_num=(_last.bar_num + 1) if _last.bar_num else len(ohlc_bars) + 1,
            )
            _bars_for_mr = ohlc_bars + [_synth_child]
            _synth_time = _next_time
            logger.debug(
                f"MaiRuay live: synthetic child appended @ {_next_time} "
                f"open={_last.close:.3f} (= mother close)"
            )

        _dbg_mr: dict = {}
        sig_mr = _mai_ruay_strat.find_signal(bars=_bars_for_mr, portfolio=portfolio, debug=_dbg_mr)

        # v2 R2 retry — only when:
        #   - v2 engine is active
        #   - round 1 produced None
        #   - we have stored r1_info from a prior SL (still within 16-bar window)
        if sig_mr is None and _r1:
            # Recompute R1's child-bar index inside the CURRENT slide window so
            # the engine's 6-bar father-start check is valid even though main.py
            # passes a rolling window. r1_bars_elapsed counts cycles since arm;
            # the R1 child sat at the last index when armed, so it has slid
            # back by r1_bars_elapsed each cycle.
            _bars_elapsed = updated_mai_ruay_state.get('r1_bars_elapsed', 0)
            _r1_with_offset = dict(_r1)
            _r1_with_offset['bar_offset_in_window'] = (len(_bars_for_mr) - 1) - _bars_elapsed
            _dbg_r2: dict = {}
            sig_mr = _mai_ruay_strat.find_signal(
                bars=_bars_for_mr, portfolio=portfolio,
                round2_info=_r1_with_offset, debug=_dbg_r2,
            )
            if sig_mr is not None:
                logger.info(
                    f"MaiRuay v2 R2 hit: bars_elapsed="
                    f"{updated_mai_ruay_state.get('r1_bars_elapsed', 0)} dir={_r1['direction']}"
                )
                # R2 fired → consume r1_info (no R3 allowed)
                updated_mai_ruay_state.pop('r1_info', None)
                updated_mai_ruay_state.pop('r1_bars_elapsed', None)
            elif _dbg_r2.get('skip'):
                skip_reasons['MAI_RUAY_R2'] = _dbg_r2['skip']

        if sig_mr is not None:
            # When the synthetic child was used, the signal's effective candle
            # time is the synthetic bar's timestamp (= mother close = child
            # start), NOT the last real bar's timestamp (which would be the
            # mother's START). Stamp it on signal.details so main.py uses the
            # right timestamp for plan_id / trade_id / timestamp_open. Without
            # this, the dashboard shows the trade at "open of mother bar"
            # instead of "open of child bar".
            if _synth_time is not None:
                try:
                    sig_mr.details = dict(sig_mr.details or {})
                    sig_mr.details['synthetic_candle_time'] = _synth_time
                except Exception:
                    pass
            candidates.append(sig_mr)
        elif _dbg_mr.get('skip'):
            skip_reasons['MAI_RUAY'] = _dbg_mr['skip']

    # UPTREND_SCANNER / DOWNTREND_SCANNER (notebook v4.2) — wrapper picks BUY
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
            'scanner_state': updated_scanner_state,  # v4.2 segment tracking
            'mai_ruay_state': updated_mai_ruay_state,  # v2 r1_info for R2 retry
            'skip_reasons': skip_reasons,       # Tier 2: per-strategy SKIP reasons
        }

    # Signal found — convert to world_state format
    logger.info(f"Signal Engine: {signal.pattern} {signal.direction} "
                f"(quality={signal.quality}, R:R={signal.rr:.2f})")

    # Map pattern to chart_type — only the 3 active strategies
    chart_type_mapping = {
        'MOUNTAIN': 'mountain',
        'MAI_RUAY': 'mai_ruay',             # Branch F (Father/Mother candle)
        'UPTREND_SCANNER': 'uptrend',       # v4.2 scanner (BUY)
        'DOWNTREND_SCANNER': 'downtrend',   # v4.2 scanner (SELL)
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
        'scanner_state': updated_scanner_state,    # v4.2 segment tracking
        'mai_ruay_state': updated_mai_ruay_state,  # v2 r1_info for R2 retry
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
