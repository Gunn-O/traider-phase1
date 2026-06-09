"""Export MT5 candles to CSV for offline / Colab backtesting.

Default behavior: dumps a notebook-compatible 6-column CSV (no header) plus
a richer 7-column "full" CSV with spread. The 6-column one matches the
load_data() helper inside strategy/XAUUSD_Backtest_*.md, so you can drop
it straight into Colab without editing the notebook.

Spread comes from MT5's per-bar `spread` field, which broker servers report
in *points*. For XAUUSD-ish symbols 1 point typically = 1 pip = 0.01 USD,
but the conversion depends on the symbol's `point` value — we look it up
and emit a `spread_usd` column so you don't have to guess.

Usage:
    python scripts/export_mt5_csv.py --tf M1 --date 2026-05-11
    python scripts/export_mt5_csv.py --tf M5 --from 2026-05-01 --to 2026-05-11
"""
from __future__ import annotations
import argparse
import csv
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import MetaTrader5 as mt5

TF_MAP = {
    "M1":  (mt5.TIMEFRAME_M1,  1),
    "M5":  (mt5.TIMEFRAME_M5,  5),
    "M15": (mt5.TIMEFRAME_M15, 15),
    "M30": (mt5.TIMEFRAME_M30, 30),
    "H1":  (mt5.TIMEFRAME_H1,  60),
    "H4":  (mt5.TIMEFRAME_H4,  240),
}


def fetch_bars(symbol: str, tf_const: int, from_utc: datetime, to_utc: datetime) -> list:
    """Fetch bars in [from_utc, to_utc). Uses copy_rates_range so we don't
    have to guess a max bar count up front."""
    if not mt5.initialize():
        print(f"mt5.initialize() failed: {mt5.last_error()}", file=sys.stderr)
        return []
    rates = mt5.copy_rates_range(symbol, tf_const, from_utc, to_utc)
    if rates is None:
        print(f"copy_rates_range returned None: {mt5.last_error()}", file=sys.stderr)
        return []
    return list(rates)


def get_point_value(symbol: str) -> float:
    """Symbol's point size (currency per 1 point). XAUUSD-ish ≈ 0.01."""
    info = mt5.symbol_info(symbol)
    return float(info.point) if info else 0.01


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="XAUUSDc")
    p.add_argument("--tf", default="M1", choices=TF_MAP.keys())
    p.add_argument("--date", help="Single UTC date, e.g. 2026-05-11 (00:00 → next 24h)")
    p.add_argument("--from", dest="from_d", help="Start UTC date YYYY-MM-DD")
    p.add_argument("--to",   dest="to_d",   help="End UTC date YYYY-MM-DD (exclusive)")
    p.add_argument("--out-dir", default="data", help="Output directory")
    args = p.parse_args()

    # Resolve UTC window
    if args.date:
        from_utc = datetime.fromisoformat(args.date).replace(tzinfo=timezone.utc)
        to_utc   = from_utc + timedelta(days=1)
    elif args.from_d and args.to_d:
        from_utc = datetime.fromisoformat(args.from_d).replace(tzinfo=timezone.utc)
        to_utc   = datetime.fromisoformat(args.to_d).replace(tzinfo=timezone.utc)
    else:
        print("Provide either --date YYYY-MM-DD or --from/--to", file=sys.stderr)
        sys.exit(1)

    tf_const, _ = TF_MAP[args.tf]
    rates = fetch_bars(args.symbol, tf_const, from_utc, to_utc)
    if not rates:
        print("No bars returned — nothing to write.")
        return

    point = get_point_value(args.symbol)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    date_tag = (args.date or f"{args.from_d}_to_{args.to_d}")
    base = f"{args.symbol}_{args.tf}_{date_tag}"

    # File 1 — notebook-compatible (no header, 6 columns)
    nb_path = out_dir / f"{base}.csv"
    with nb_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for r in rates:
            t = datetime.fromtimestamp(int(r["time"]), tz=timezone.utc)
            # ISO format without timezone marker — load_data uses pd.to_datetime
            # which handles both, but stripping the +00:00 keeps the CSV slim
            # and matches what most XAUUSD M1 CSVs in the wild look like.
            ts_str = t.strftime("%Y-%m-%d %H:%M:%S")
            w.writerow([
                ts_str,
                f"{float(r['open']):.3f}",
                f"{float(r['high']):.3f}",
                f"{float(r['low']):.3f}",
                f"{float(r['close']):.3f}",
                int(r["tick_volume"]),
            ])

    # File 2 — full (header + spread + spread_usd)
    full_path = out_dir / f"{base}_full.csv"
    with full_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["time_utc", "open", "high", "low", "close", "tick_volume", "spread_points", "spread_usd"])
        for r in rates:
            t = datetime.fromtimestamp(int(r["time"]), tz=timezone.utc)
            spread_points = int(r["spread"])
            spread_usd = round(spread_points * point, 5)
            w.writerow([
                t.strftime("%Y-%m-%d %H:%M:%S"),
                f"{float(r['open']):.3f}",
                f"{float(r['high']):.3f}",
                f"{float(r['low']):.3f}",
                f"{float(r['close']):.3f}",
                int(r["tick_volume"]),
                spread_points,
                f"{spread_usd:.5f}",
            ])

    print(f"✓ Wrote {len(rates)} bars")
    print(f"  notebook:  {nb_path}")
    print(f"  full:      {full_path}")
    print(f"  symbol point value = {point}  (spread_usd = spread_points × point)")

    # Quick stats
    spreads = [int(r["spread"]) for r in rates]
    if spreads:
        avg_sp = sum(spreads) / len(spreads)
        print(f"  spread stats: min={min(spreads)} max={max(spreads)} avg={avg_sp:.1f} (points)")


if __name__ == "__main__":
    main()
