"""One-day Scanner backtest replay using the LIVE engine code.

Runs UPTREND_SCANNER / DOWNTREND_SCANNER over a single UTC day at M1, M5, M15,
M30 — same detectors the live bot uses, same stateful segment + stop_segments
behavior, same TP/SL/lot math. Prints a per-TF trade list and a summary
so you can compare against a Colab notebook backtest.

Usage:
    python scripts/backtest_scanner_day.py --date 2026-05-11
"""
from __future__ import annotations
import argparse
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import MetaTrader5 as mt5

from utils.xauusd_signal import OHLC, ScannerSegmentState
from strategies.uptrend_downtrend_scanner import find_signal

TF_MAP = {
    "M1":  (mt5.TIMEFRAME_M1,  1),
    "M5":  (mt5.TIMEFRAME_M5,  5),
    "M15": (mt5.TIMEFRAME_M15, 15),
    "M30": (mt5.TIMEFRAME_M30, 30),
}


def to_ohlc(rates):
    return [
        OHLC(
            time=datetime.fromtimestamp(int(r["time"]), tz=timezone.utc),
            open=float(r["open"]),
            high=float(r["high"]),
            low=float(r["low"]),
            close=float(r["close"]),
            bar_num=i + 1,
        )
        for i, r in enumerate(rates)
    ]


def simulate_trade(signal, future_bars):
    """Walk forward through future_bars until TP or SL is hit.

    v3.7 behavior: check TP/SL on the entry bar too (was a bug in v3.4-v3.6
    where the entry bar was skipped, causing same-bar SL hits to be recorded
    as WIN). Both-hit conflict resolves to whichever is closer to entry; on
    equal distance, SL wins (notebook conservative rule).

    Returns (result, close_price, close_time, bars_to_close, mae_pip, mfe_pip).
    """
    entry = signal.entry
    tp = signal.tp_order
    sl = signal.sl
    is_buy = (signal.direction == "BUY")
    mae = 0.0
    mfe = 0.0
    for i, b in enumerate(future_bars):  # v3.7: include entry bar (idx 0)
        if is_buy:
            adv = max(0.0, entry - b.low) * 100
            fav = max(0.0, b.high - entry) * 100
            tp_hit = b.high >= tp
            sl_hit = b.low <= sl
        else:
            adv = max(0.0, b.high - entry) * 100
            fav = max(0.0, entry - b.low) * 100
            tp_hit = b.low <= tp
            sl_hit = b.high >= sl
        mae = max(mae, adv)
        mfe = max(mfe, fav)
        if tp_hit and sl_hit:
            # Conservative: SL wins on tie / closer
            tp_d = abs(tp - entry)
            sl_d = abs(entry - sl)
            tp_first = tp_d < sl_d  # strict <
        else:
            tp_first = tp_hit
        if tp_first:
            return ("WIN", tp, b.time, i, mae, mfe)
        if sl_hit:
            return ("LOSS", sl, b.time, i, mae, mfe)
    return ("OPEN", None, None, len(future_bars) - 1, mae, mfe)


def replay(rates, tf_name: str, portfolio: float = 1000.0,
           live_mode: bool = False, dup_pip: float = 50.0):
    """Replay one TF: for each bar, run Scanner with persistent state.
    Trade simulation walks forward until TP/SL hit. On LOSS, segment is
    added to scanner_state.stopped_*_segments (matches new live behavior).

    live_mode: if True, only the last 55 bars are passed to the detector
               (matches the LIVE bot's CANDLES_LOOKBACK=55 fetch — no lookback
                for C5/C6). If False, lookback bars are included (matches the
                notebook backtest design).
    dup_pip:   G2-style duplicate filter — skip a new entry if it's within
               ±dup_pip of the most recent entry's price. Mirrors the live
               G2Prefilter duplicate guard.
    """
    bars = to_ohlc(rates)
    if len(bars) < 55:
        return []
    state = ScannerSegmentState()
    trades = []
    last_entry_price = None
    open_trade_end_idx = -1
    for end_idx in range(54, len(bars)):
        if end_idx < open_trade_end_idx:
            continue
        # Live mode trims the window so the detector gets exactly the same view
        # the LIVE bot would have (no lookback → C5/C6 effectively skipped).
        if live_mode:
            start = max(0, end_idx + 1 - 55)
            window = bars[start: end_idx + 1]
        else:
            window = bars[: end_idx + 1]
        sig = find_signal(window, portfolio=portfolio, state=state)
        if sig is None:
            continue
        # G2 duplicate filter — skip entries near a recent entry price
        if last_entry_price is not None and abs(sig.entry - last_entry_price) * 100 < dup_pip:
            continue
        last_entry_price = sig.entry
        result, close_price, close_time, bars_held, mae, mfe = simulate_trade(sig, bars[end_idx:])
        seg = (sig.details or {}).get("segment_id")
        pnl = 0.0
        if result == "WIN":
            pnl = sig.reward_pip * sig.lot
        elif result == "LOSS":
            pnl = -sig.risk_pip * sig.lot
        trades.append({
            "tf": tf_name,
            "entry_time": bars[end_idx].time,
            "direction": sig.direction,
            "entry": sig.entry,
            "sl": sig.sl,
            "tp": sig.tp_order,
            "lot": sig.lot,
            "rr": sig.rr,
            "result": result,
            "close_time": close_time,
            "close_price": close_price,
            "bars_held": bars_held,
            "pnl_pip": (sig.reward_pip if result == "WIN" else -sig.risk_pip if result == "LOSS" else 0),
            "pnl_usd": round(pnl, 2),
            "mae_pip": round(mae, 1),
            "mfe_pip": round(mfe, 1),
            "segment_id": seg,
        })
        if close_time is not None:
            # Block re-scan until the closing bar (1-trade-at-a-time)
            open_trade_end_idx = end_idx + bars_held + 1
        # Stateful stop: notebook v3.7 marks segment STOPPED on LOSS.
        if result == "LOSS" and seg:
            if sig.direction == "BUY":
                state.stopped_up_segments.add(seg)
            else:
                state.stopped_down_segments.add(seg)
    return trades


def print_trades(tf: str, trades: list):
    print(f"\n=== {tf}  ({len(trades)} signals) ===")
    if not trades:
        print("  (no signals)")
        return
    print(f"  {'entry_time':<22} {'dir':<5} {'entry':>10} {'sl':>10} {'tp':>10} {'result':<7} {'pip':>8} {'usd':>9} {'bars':>5} {'mae':>6} {'mfe':>6}  segment")
    for t in trades:
        et = t["entry_time"].strftime("%Y-%m-%d %H:%M")
        pip = f"{t['pnl_pip']:+.0f}"
        usd = f"{t['pnl_usd']:+.2f}"
        seg_short = (t["segment_id"] or "")[-8:]
        print(f"  {et:<22} {t['direction']:<5} {t['entry']:>10.2f} {t['sl']:>10.2f} {t['tp']:>10.2f} {t['result']:<7} {pip:>8} {usd:>9} {t['bars_held']:>5} {t['mae_pip']:>6.0f} {t['mfe_pip']:>6.0f}  {seg_short}")
    wins = sum(1 for t in trades if t["result"] == "WIN")
    losses = sum(1 for t in trades if t["result"] == "LOSS")
    opens = sum(1 for t in trades if t["result"] == "OPEN")
    net_pip = sum(t["pnl_pip"] for t in trades if t["result"] in ("WIN", "LOSS"))
    net_usd = sum(t["pnl_usd"] for t in trades if t["result"] in ("WIN", "LOSS"))
    wr = wins / (wins + losses) if (wins + losses) > 0 else 0
    print(f"  → W:{wins} L:{losses} OPEN:{opens}  WR={wr:.0%}  net_pip={net_pip:+.0f}  net_usd={net_usd:+.2f}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="XAUUSDc")
    p.add_argument("--date", required=True, help="UTC date YYYY-MM-DD")
    p.add_argument("--tfs", default="M1,M5,M15,M30")
    p.add_argument("--live-mode", action="store_true",
                   help="Trim window to 55 bars (matches LIVE bot CANDLES_LOOKBACK=55) instead of full notebook lookback")
    p.add_argument("--dup-pip", type=float, default=50.0,
                   help="G2-style duplicate filter threshold in pip (default 50)")
    args = p.parse_args()

    if not mt5.initialize():
        print(f"mt5.initialize() failed: {mt5.last_error()}", file=sys.stderr)
        sys.exit(1)

    from_utc = datetime.fromisoformat(args.date).replace(tzinfo=timezone.utc)
    to_utc = from_utc + timedelta(days=1)

    tfs = [t.strip() for t in args.tfs.split(",") if t.strip() in TF_MAP]
    print(f"Symbol: {args.symbol}")
    print(f"Date:   {args.date} UTC  ({from_utc.isoformat()} → {to_utc.isoformat()})")
    print(f"TFs:    {tfs}")
    print(f"Note: M1 isn't whitelisted for Scanner in config but we run it anyway for diagnostics.")

    grand_total = {"wins": 0, "losses": 0, "opens": 0, "net_usd": 0.0}
    for tf_name in tfs:
        tf_const, tf_min = TF_MAP[tf_name]
        # Fetch with 80-bar lead-in for the 55-bar window
        lead_bars = 80
        fetch_from = from_utc - timedelta(minutes=tf_min * lead_bars)
        rates = mt5.copy_rates_range(args.symbol, tf_const, fetch_from, to_utc)
        if rates is None or len(rates) == 0:
            print(f"\n=== {tf_name} === no data")
            continue
        # Filter trades to entries within [from_utc, to_utc) only — but window
        # itself can include lead-in bars.
        trades = replay(rates, tf_name, live_mode=args.live_mode, dup_pip=args.dup_pip)
        # Keep only trades that ENTERED on the target day
        day_trades = [t for t in trades if from_utc <= t["entry_time"] < to_utc]
        print_trades(tf_name, day_trades)
        for t in day_trades:
            if t["result"] == "WIN":   grand_total["wins"] += 1
            elif t["result"] == "LOSS": grand_total["losses"] += 1
            elif t["result"] == "OPEN": grand_total["opens"] += 1
            grand_total["net_usd"] += t["pnl_usd"]

    g = grand_total
    total = g["wins"] + g["losses"]
    print(f"\n=== GRAND TOTAL ===")
    print(f"  W:{g['wins']} L:{g['losses']} OPEN:{g['opens']}  "
          f"WR={g['wins']/total:.0%}" if total else "  no completed trades",
          f"  net_usd={g['net_usd']:+.2f}")


if __name__ == "__main__":
    main()
