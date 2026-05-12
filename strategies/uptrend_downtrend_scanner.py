"""XAUUSD Uptrend / Downtrend Scanner v3.4 — Phase II wrapper.

The criteria functions and `_detect_uptrend_scanner` / `_detect_downtrend_scanner`
live in `utils/xauusd_signal.py` (additive — no existing function modified).
This file only exposes the `find_signal()` entry point that signal_engine.py
calls. UPTREND_SCANNER takes priority over DOWNTREND_SCANNER (configurable
later via priorities in strategies.json).
"""
from typing import List, Optional

from utils.xauusd_signal import (
    OHLC, Signal, ScannerSegmentState,
    _detect_uptrend_scanner,
    _detect_downtrend_scanner,
)


def find_signal(
    bars: List[OHLC],
    portfolio: float = 1000.0,
    debug: Optional[dict] = None,
    state: Optional[ScannerSegmentState] = None,
    **_kwargs,
) -> Optional[Signal]:
    """BUY first, fall back to SELL.

    debug: optional dict — when supplied, fills 'skip' with the reason from the
           SELL detector (since BUY is tried first; if SELL also fails, that's
           the deepest signal). For visibility into both paths separately,
           callers can pass nested dicts via debug={'buy': {}, 'sell': {}}.
    state: optional ScannerSegmentState — threads through to both BUY and SELL
           detectors so segment tracking + stop_segments work in LIVE mode.
    """
    if len(bars) < 55:
        if debug is not None:
            debug['skip'] = f"bars {len(bars)} < 55"
        return None
    buy_dbg = debug.get('buy') if isinstance(debug, dict) and 'buy' in debug else (debug or None)
    sig = _detect_uptrend_scanner(bars, portfolio, debug=buy_dbg, state=state)
    if sig is not None:
        return sig
    sell_dbg = debug.get('sell') if isinstance(debug, dict) and 'sell' in debug else debug
    return _detect_downtrend_scanner(bars, portfolio, debug=sell_dbg, state=state)
