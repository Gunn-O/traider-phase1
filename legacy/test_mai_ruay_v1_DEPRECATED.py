"""
⛔ DEPRECATED — tests the OLD V2.04 engine (SL 40% / TP 45% / TP30-SL45 / Round 2 /
   3-entry split), all removed in the MaiRuay-v2 rewrite. Superseded by the geometry
   parity gate scripts/parity_mairuay_v2.py (vs reference/mai_ruay_v2_snapshot/).
   Kept for reference; do not run against the current strategies/mai_ruay.py.

Smoke test สำหรับ strategies/mai_ruay.py (v2.04 engine)

ตรวจสอบว่า engine v2.04 ทำงานครบ logic + ไม่ crash บน CSV M1 จริง:
  - find_father Pass 1 (สีเดียวห้ามแทรก, Vol Ratio >1, body criteria)
  - validate_mother (3-25% ของ R55)
  - 3 entries ครบ (split lot/3, MARKET/LIMIT ถูก bucket)
  - SL = 40% × father_body
  - TP = 45% × father_body
  - TP30/SL45 special trigger ได้
  - TP < 200 pip → skip
  - Signal field ใหม่ (entries, is_round2, father_pass, vol_ratio) มีค่า

วิธีใช้:
    python -m tests.test_mai_ruay_v2
"""
from __future__ import annotations
import sys, os
from pathlib import Path

# Ensure project root in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime
from utils.xauusd_signal import OHLC
from strategies.mai_ruay import find_signal, _analyze_bar


CSV_PATHS = [
    'data/XAUUSDc_M1_2026-05-11_full.csv',
    'data/XAUUSDc_M1_2026-05-15_full.csv',
]


def load_bars(path: str) -> list[OHLC]:
    bars = []
    with open(path, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f, start=1):
            parts = line.strip().split(',')
            if len(parts) < 5:
                continue
            try:
                bars.append(OHLC(
                    time  = parts[0],
                    open  = float(parts[1]),
                    high  = float(parts[2]),
                    low   = float(parts[3]),
                    close = float(parts[4]),
                    bar_num = i,
                ))
            except ValueError:
                continue
    return bars


def main():
    bars = []
    for p in CSV_PATHS:
        if not os.path.exists(p):
            print(f'⚠️  CSV not found: {p}')
            continue
        b = load_bars(p)
        print(f'Loaded {len(b)} bars from {p}')
        bars.extend(b)
    if not bars:
        print('❌ ไม่มี CSV ที่ใช้ test ได้')
        sys.exit(1)
    print(f'Total: {len(bars)} bars  ({bars[0].time} → {bars[-1].time})')

    # Slide ทุก bar — รัน find_signal ที่ bars[:i+1] ทุก position
    signals = []
    for i in range(55, len(bars)):
        sig = find_signal(bars[:i+1], portfolio=1000.0)
        if sig is not None:
            signals.append((i, sig))

    print(f'\nFound {len(signals)} signals')

    if not signals:
        print('⚠️  ไม่มี signal เลย — เช็คว่า logic เข้มไปไหม')
        return

    # ตรวจ field ใหม่
    print('\n─── Sample 5 signals ───')
    for idx, (bar_idx, sig) in enumerate(signals[:5]):
        print(f'\n[{idx+1}] bar_idx={bar_idx} time={bars[bar_idx].time}')
        print(f'    pattern   : {sig.pattern}')
        print(f'    direction : {sig.direction}  quality: {sig.quality}')
        print(f'    entry/sl/tp: {sig.entry:.3f} / {sig.sl:.3f} / {sig.tp_order:.3f}')
        print(f'    rr={sig.rr:.2f}  risk_pip={sig.risk_pip:.0f}  reward_pip={sig.reward_pip:.0f}')
        print(f'    lot={sig.lot}  R55={sig.R55:.0f}')
        print(f'    is_round2={sig.is_round2}  father_pass={sig.father_pass!r}  vol_ratio={sig.vol_ratio}')
        d = sig.details
        print(f'    father_bars={d["father_bars"]}  father_pct_r55={d["father_pct_r55"]:.1f}%')
        print(f'    mother_pct_r55={d["mother_pct_r55"]:.1f}%  ({d["mother_quality"]})')
        print(f'    tp_name={sig.tp_name}  sl_label={d["sl_label"]}')
        print(f'    order_type(first)={d["order_type"]}  pending_bars={d["pending_bars"]}')
        print(f'    entries ({len(sig.entries)}):')
        for j, ep in enumerate(sig.entries):
            kind = 'MKT' if ep.is_market else 'LMT'
            ep_sl_dist = abs(ep.price - ep.sl)
            ep_tp_dist = abs(ep.tp - ep.price)
            ep_rr = ep_tp_dist / ep_sl_dist if ep_sl_dist > 0 else 0
            print(f'      [{j+1}] {kind}  E={ep.price:.3f}  TP={ep.tp:.3f}  SL={ep.sl:.3f}  '
                  f'RR={ep_rr:.2f}  lot={ep.lot}  {ep.label}')

    # ─── Invariant checks ───
    print('\n─── Invariant checks ───')
    errs = []
    for i, (bar_idx, sig) in enumerate(signals):
        # 1. ต้องมี 3 entries
        if not sig.entries or len(sig.entries) != 3:
            errs.append(f'[{i}] entries len ≠ 3 (got {len(sig.entries) if sig.entries else 0})')
        # 2. ผลรวม lot ≈ sig.lot (±0.03 round error)
        if sig.entries:
            total_lot = sum(ep.lot for ep in sig.entries)
            if abs(total_lot - sig.lot) > 0.03:
                errs.append(f'[{i}] sum(entries.lot)={total_lot} ≠ sig.lot={sig.lot}')
        # 3. SL distance > 0
        if sig.risk_pip <= 0:
            errs.append(f'[{i}] risk_pip {sig.risk_pip} <= 0')
        # 4. TP ≥ 200 pip (filter ที่ใช้)
        if sig.reward_pip < 200:
            errs.append(f'[{i}] reward_pip {sig.reward_pip} < 200 (filter ไม่ทำงาน)')
        # 5. quality ∈ {'✓', '~60%⚠️'}
        if sig.quality not in ('✓', '~60%⚠️'):
            errs.append(f'[{i}] quality {sig.quality!r} unexpected')
        # 6. direction ตรงกับ father direction (BUY = father DOWN, SELL = father UP)
        d = sig.details
        # 7. father_pct_r55 > 60 (Pass1) หรือ > 35 (R2)
        if not sig.is_round2 and d['father_pct_r55'] <= 60:
            errs.append(f'[{i}] Pass1 father_pct_r55 {d["father_pct_r55"]} ≤ 60')
        # 8. mother_pct_r55 ∈ [2, 25]
        if not (2 <= d['mother_pct_r55'] <= 25):
            errs.append(f'[{i}] mother_pct_r55 {d["mother_pct_r55"]} out of [2,25]')
        # 9. ทุก entry มี TP/SL ครบ (ไม่ใช่ 0.0 default)
        for j, ep in enumerate(sig.entries or []):
            if ep.tp == 0.0 or ep.sl == 0.0:
                errs.append(f'[{i}] entry[{j}] tp/sl missing (tp={ep.tp} sl={ep.sl})')
            # SL ของ entry ต้อง = sig.sl เสมอ (notebook spec)
            if abs(ep.sl - sig.sl) > 1e-6:
                errs.append(f'[{i}] entry[{j}] sl {ep.sl} ≠ sig.sl {sig.sl}')
            # TP per-entry RR ≥ 1.0 (per-entry adjustment guarantees)
            ep_sl_dist = abs(ep.price - ep.sl)
            ep_tp_dist = abs(ep.tp - ep.price)
            ep_rr = ep_tp_dist / ep_sl_dist if ep_sl_dist > 0 else 0
            if ep_rr < 1.0 - 1e-3:
                errs.append(f'[{i}] entry[{j}] RR {ep_rr:.3f} < 1.0 (adjustment broken)')

    if errs:
        print(f'❌ {len(errs)} errors:')
        for e in errs[:20]:
            print(f'  {e}')
        sys.exit(1)
    else:
        print(f'✅ All {len(signals)} signals pass invariants')

    # ─── Distribution ───
    print('\n─── Signal distribution ───')
    n_buy  = sum(1 for _, s in signals if s.direction == 'BUY')
    n_sell = sum(1 for _, s in signals if s.direction == 'SELL')
    print(f'BUY={n_buy}  SELL={n_sell}')

    n_market_first = sum(1 for _, s in signals if s.entries[0].is_market)
    n_limit_first  = len(signals) - n_market_first
    print(f'1st entry MARKET={n_market_first}  LIMIT={n_limit_first}')

    n_tp_45 = sum(1 for _, s in signals if 'TP 45%' in s.tp_name)
    n_tp_30 = sum(1 for _, s in signals if 'TP 30%' in s.tp_name)
    print(f'TP 45% (default)={n_tp_45}  TP 30% (special)={n_tp_30}')

    print('\n✅ Smoke test complete')


if __name__ == '__main__':
    main()
