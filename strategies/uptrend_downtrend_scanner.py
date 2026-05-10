"""XAUUSD Uptrend / Downtrend Scanner v3.4 — Phase II wrapper.

The criteria functions and `_detect_uptrend_scanner` / `_detect_downtrend_scanner`
live in `utils/xauusd_signal.py` (additive — no existing function modified).
This file only exposes the `find_signal()` entry point that signal_engine.py
calls. UPTREND_SCANNER takes priority over DOWNTREND_SCANNER (configurable
later via priorities in strategies.json).
"""
from typing import List, Optional

from utils.xauusd_signal import (
    OHLC, Signal,
    _detect_uptrend_scanner,
    _detect_downtrend_scanner,
)


def find_signal(bars: List[OHLC], portfolio: float = 1000.0, **_kwargs) -> Optional[Signal]:
    if len(bars) < 55:
        return None
    sig = _detect_uptrend_scanner(bars, portfolio)
    if sig is not None:
        return sig
    return _detect_downtrend_scanner(bars, portfolio)
