#!/usr/bin/env python
# ============================================================================
# scripts/smoke_mairuay_v2_pipeline.py — live-path contract smoke for MaiRuay v2
# ----------------------------------------------------------------------------
# Drives the REAL run_signal_engine() with candles_by_tf (the exact shape main.py
# passes), then replicates main.py's multi-entry order construction to prove the
# v2 Signal / EntryPoint / details contract feeds the pipeline without KeyError /
# AttributeError. Does NOT touch any broker — pure in-memory.
#
# exit 0 iff: engine returns a MAI_RUAY_M1 signal (chart_type/technique = mai_ruay),
#             entries populated, and the order dicts + pending fields build clean.
# ============================================================================
from __future__ import annotations

import os
import sys
from datetime import timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP = os.path.join(REPO_ROOT, "reference", "mai_ruay_v2_snapshot")
DATA = os.path.join(SNAP, "data", "XAUUSD_M1_2026-06-09.csv")
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, SNAP)

# backtest mode = no live synthetic-bar replacement (analyse the closed bar as-is)
os.environ["TRAIDER_BACKTEST_ACTIVE"] = "1"
os.environ["BACKTEST_TIMEFRAME"] = "M1"

from bt.data import load_csv                       # noqa: E402
from strategies import mai_ruay as repo            # noqa: E402
from utils.xauusd_signal import OHLC               # noqa: E402
from utils.signal_engine import run_signal_engine  # noqa: E402

PORTFOLIO = 1000.0


def _candle(b):
    # real candles carry tz-aware timestamps; bt's pandas Timestamp is tz-naive
    ts = b.time.to_pydatetime().replace(tzinfo=timezone.utc)
    return {"timestamp": ts, "open": b.open, "high": b.high,
            "low": b.low, "close": b.close, "volume": b.volume or 1}


def main() -> int:
    bars = load_csv(DATA)
    repo_bars = [OHLC(time=str(b.time), open=b.open, high=b.high, low=b.low,
                      close=b.close, bar_num=i + 1) for i, b in enumerate(bars)]

    # find the first bar where MaiRuay v2 fires (deterministic on this data)
    sig_idx = None
    for i in range(60, len(bars)):
        if repo.find_signal(repo_bars[max(0, i - 160):i + 1], portfolio=PORTFOLIO):
            sig_idx = i
            break
    if sig_idx is None:
        print("SMOKE FAIL: no MaiRuay v2 signal found in reference data")
        return 1

    candles = [_candle(b) for b in bars[:sig_idx + 1]]
    world_state = run_signal_engine(candles_by_tf={"M1": candles}, portfolio=PORTFOLIO)

    signal = world_state.get("signal")
    checks = []
    checks.append(("engine returned a signal", signal is not None))
    if signal is None:
        print(f"SMOKE FAIL @bar {sig_idx}: run_signal_engine returned no signal "
              f"(skip_reasons={world_state.get('skip_reasons')})")
        return 1

    checks.append(("pattern == MAI_RUAY_M1", signal.pattern == "MAI_RUAY_M1"))
    checks.append(("chart_type == mai_ruay", world_state.get("chart_type") == "mai_ruay"))
    checks.append(("technique == mai_ruay", world_state.get("technique_candidate") == "mai_ruay"))
    checks.append(("entries populated", bool(getattr(signal, "entries", None))))
    checks.append(("is_round2 is False", signal.is_round2 is False))

    # ── replicate main.py multi-entry order construction (main.py ~1134-1150) ──
    d = signal.details or {}
    orders = []
    for ix, ep in enumerate(signal.entries):
        lot = ep.lot if ep.lot and ep.lot > 0 else 0.01
        rr = (abs(ep.tp - ep.price) / abs(ep.price - ep.sl)) if abs(ep.price - ep.sl) > 0 else 0.0
        orders.append({
            "order_num": ix + 1,
            "order_type": "MARKET" if ep.is_market else "LIMIT",
            "entry": ep.price, "sl": ep.sl, "tp": ep.tp,
            "lot": lot, "rr_ratio": rr, "entry_label": ep.label,
        })
    # pending fields main.py reads off details (main.py ~1306-1307)
    pending_bars = int(d.get("pending_bars", 5))
    tp_cancel_buf = float(d.get("tp_cancel_buffer_pips", 0.0))
    order_type_first = d.get("order_type")

    checks.append(("orders built", len(orders) == len(signal.entries)))
    checks.append(("details.order_type set", order_type_first in ("MARKET", "LIMIT")))
    checks.append(("details.pending_bars == 5", pending_bars == 5))
    checks.append(("details.tp_cancel_buffer_pips = 5%R55",
                   abs(tp_cancel_buf - signal.R55 * 0.05) < 1e-6))

    print("=" * 60)
    print(f"  MaiRuay v2 live-path smoke @ reference bar {sig_idx}")
    print("=" * 60)
    print(f"  {signal.pattern} {signal.direction}  entry={signal.entry:.3f} "
          f"sl={signal.sl:.3f} tp={signal.tp_order:.3f} rr={signal.rr:.2f} lot={signal.lot}")
    print(f"  chart_type={world_state.get('chart_type')} "
          f"technique={world_state.get('technique_candidate')}")
    print(f"  orders={len(orders)} order_type={order_type_first} "
          f"pending_bars={pending_bars} tp_cancel_buf={tp_cancel_buf:.2f}pip")
    for o in orders:
        print(f"    #{o['order_num']} {o['order_type']} E={o['entry']:.3f} "
              f"SL={o['sl']:.3f} TP={o['tp']:.3f} lot={o['lot']} RR={o['rr_ratio']:.2f}")
    print("-" * 60)
    ok = all(v for _, v in checks)
    for name, v in checks:
        print(f"  [{'ok' if v else 'FAIL'}] {name}")
    print("=" * 60)
    print("  SMOKE PASS" if ok else "  SMOKE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
