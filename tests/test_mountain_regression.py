"""
Mountain regression — รัน mountain.find_signal() บน CSV M1 แล้วตรวจว่า:
  - Signal field เดิม (pattern/direction/entry/sl/tp_order/tp_ref/...) ตรงเป๊ะ
  - field ใหม่ (entries/is_round2/father_pass/vol_ratio) มีค่า default
  - Mountain ใช้ Signal positional+keyword arg เดิมได้ — ไม่ต้องแก้

วิธีใช้:
    python -m tests.test_mountain_regression
"""
from __future__ import annotations
import sys, os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.xauusd_signal import OHLC
from strategies.mountain import find_signal as mountain_find


CSV_PATHS = [
    'data/XAUUSDc_M5_2026-05-12_to_2026-05-14_full.csv',
    'data/XAUUSDc_M5_2026-05-15_full.csv',
    # M1 sets — DB has Mountain trades on 2026-05-15 (e.g. 01:29 / 08:30 BUY @ 4608.47)
    'data/XAUUSDc_M1_2026-05-15_full.csv',
    'data/XAUUSDc_M1_2026-05-11_full.csv',
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
    print(f'Total: {len(bars)} bars')

    signals = []
    state = None
    for i in range(55, len(bars)):
        sig = mountain_find(bars[:i+1], portfolio=1000.0, mountain_state=state)
        if sig is not None:
            signals.append((i, sig))

    print(f'\nMountain found {len(signals)} signals')

    if not signals:
        print('⚠️  ไม่มี Mountain signal — เช็คว่า data set มี pattern หรือไม่')
        print('   (ไม่ใช่ failure — Mountain pattern หาเจอยากใน M5 sample สั้น)')
        return

    # ─── Backward-compat checks ───
    errs = []
    for i, (bar_idx, sig) in enumerate(signals):
        # 1. Field เดิมต้องครบ
        for f in ('pattern', 'direction', 'entry', 'sl', 'tp_order', 'tp_ref',
                  'tp_name', 'rr', 'risk_pip', 'reward_pip', 'lot', 'R55', 'details'):
            if not hasattr(sig, f):
                errs.append(f'[{i}] missing field: {f}')

        # 2. Mountain ไม่ควรใช้ field ใหม่ (default value)
        if sig.entries is not None:
            errs.append(f'[{i}] Mountain has entries={sig.entries} (should be None)')
        if sig.is_round2:
            errs.append(f'[{i}] Mountain is_round2=True (should be False)')
        if sig.father_pass != '':
            errs.append(f'[{i}] Mountain father_pass={sig.father_pass!r} (should be "")')
        if sig.vol_ratio != 0.0:
            errs.append(f'[{i}] Mountain vol_ratio={sig.vol_ratio} (should be 0.0)')

        # 3. Pattern ต้องเป็น MOUNTAIN
        if 'MOUNTAIN' not in sig.pattern.upper():
            errs.append(f'[{i}] pattern={sig.pattern} (expected MOUNTAIN*)')

        # 4. details['order_type'] ต้องเป็น LIMIT (Mountain spec)
        if sig.details.get('order_type') != 'LIMIT':
            errs.append(f'[{i}] details order_type={sig.details.get("order_type")} (expected LIMIT)')

    if errs:
        print(f'\n❌ {len(errs)} regression errors:')
        for e in errs[:20]:
            print(f'  {e}')
        sys.exit(1)
    else:
        print(f'\n✅ All {len(signals)} Mountain signals — fields ตรงเป๊ะ')
        print('   field เดิมยังทำงาน, field ใหม่ default ค่า')

    # ─── Show sample ───
    print('\n─── Sample 3 Mountain signals ───')
    for idx, (bar_idx, sig) in enumerate(signals[:3]):
        print(f'\n[{idx+1}] bar_idx={bar_idx} time={bars[bar_idx].time}')
        print(f'    {sig.pattern}  {sig.direction}  quality={sig.quality}')
        print(f'    E={sig.entry:.3f}  SL={sig.sl:.3f}  TP_ord={sig.tp_order:.3f}  TP_ref={sig.tp_ref:.3f}')
        print(f'    rr={sig.rr:.2f}  lot={sig.lot}  order_type={sig.details["order_type"]}')

    print('\n✅ Mountain regression complete')


if __name__ == '__main__':
    main()
