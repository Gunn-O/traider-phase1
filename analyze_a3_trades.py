"""
Analyze A3 Mountain Trades

ตรวจสอบว่า A3 mountain trades มี entry/SL/TP ที่ถูกต้องตาม strategy หรือไม่
"""

import json
from datetime import datetime

# Load backtest results
with open('backtest/results/backtest_7days_claude.json', 'r') as f:
    results = json.load(f)

print("\n" + "="*70)
print("A3 MOUNTAIN TRADES ANALYSIS")
print("="*70)

# Filter A3 trades
a3_trades = [t for t in results['trades'] if t['condition'] == 'A3_mountain']

print(f"\nTotal A3 trades: {len(a3_trades)}")
if len(a3_trades) == 0:
    print("No A3 trades found!")
    exit(0)

wins = sum(1 for t in a3_trades if t['result'] == 'WIN')
losses = sum(1 for t in a3_trades if t['result'] == 'LOSS')
win_rate = (wins / len(a3_trades) * 100) if len(a3_trades) > 0 else 0

print(f"Win: {wins}, Loss: {losses}, Win Rate: {win_rate:.1f}%")
print(f"\n{'='*70}")

# Detailed analysis
for i, trade in enumerate(a3_trades, 1):
    print(f"\n📊 Trade #{i}: {trade['action']} @ ${trade['entry']:.2f}")
    print(f"{'─'*70}")
    print(f"Timestamp: {trade['timestamp']}")
    print(f"Pattern: {trade['pattern']}")
    print(f"RSI: {trade['rsi']:.1f} ({trade['rsi_zone']})")
    print(f"H1 Trend: {trade['h1_trend']}")
    print(f"Session: {trade['session']}")
    print(f"Confidence: {trade['confidence']:.3f}")

    print(f"\n💰 Trade Setup:")
    entry = trade['entry']
    sl = trade['sl']
    tp1 = trade['tp1']

    sl_distance = abs(entry - sl)
    tp_distance = abs(tp1 - entry)
    rr_ratio = tp_distance / sl_distance if sl_distance > 0 else 0

    print(f"   Entry:  ${entry:.2f}")
    print(f"   SL:     ${sl:.2f} (distance: ${sl_distance:.2f})")
    print(f"   TP1:    ${tp1:.2f} (distance: ${tp_distance:.2f})")
    print(f"   R:R:    1:{rr_ratio:.2f}")
    print(f"   Lot:    {trade['lot']:.2f}")

    # Calculate mountain height based on SL/TP
    # Strategy: TP1 = ⅓ ของยอดภูเขา, SL = ที่ฐาน
    if trade['action'] == 'BUY':
        # TP1 = entry + (mountain_height * 0.4) based on our Mock Agent
        # So: mountain_height = (tp1 - entry) / 0.4
        implied_mountain_height = (tp1 - entry) / 0.4
        print(f"\n🏔️ Mountain Analysis:")
        print(f"   Implied mountain height: ${implied_mountain_height:.2f}")
        print(f"   Entry at base: ${entry:.2f}")
        print(f"   Expected peak: ~${entry + implied_mountain_height:.2f}")
        print(f"   TP1 (40% of height): ${tp1:.2f}")

    print(f"\n📈 Result:")
    print(f"   Outcome: {trade['result']}")
    print(f"   P&L: ${trade['pnl']:.2f}")
    print(f"   Exit Price: ${trade['exit_price']:.2f}")
    print(f"   Close Reason: {trade['close_reason']}")
    print(f"   Duration: {trade['duration_candles']} candles")

    # Analysis
    print(f"\n🔍 Assessment:")

    # Check if entry is reasonable (not too far from base)
    if trade['action'] == 'BUY':
        if sl_distance < 15:
            print(f"   ⚠️  SL distance very tight: ${sl_distance:.2f} (< $15)")
        elif sl_distance > 30:
            print(f"   ⚠️  SL distance too wide: ${sl_distance:.2f} (> $30)")
        else:
            print(f"   ✓ SL distance reasonable: ${sl_distance:.2f}")

        if rr_ratio < 2.0:
            print(f"   ⚠️  R:R below 1:2 - ${rr_ratio:.2f}")
        else:
            print(f"   ✓ R:R acceptable: 1:{rr_ratio:.2f}")

        # Check if exit was close to TP or SL
        if trade['result'] == 'LOSS':
            if trade['close_reason'] == 'SL_HIT':
                print(f"   ❌ Hit SL - ราคาลงทะลุฐาน")
            elif trade['close_reason'] == 'TIMEOUT':
                price_movement = trade['exit_price'] - entry
                print(f"   ⏱️  Timeout - ราคาเคลื่อนไหว ${price_movement:.2f} ({(price_movement/sl_distance)*100:.1f}% ของ SL)")
                if price_movement < 0:
                    print(f"      → ราคาลงจากจุดเข้า แต่ยังไม่ถึง SL")
        elif trade['result'] == 'WIN':
            if trade['close_reason'] == 'TP1_HIT':
                print(f"   ✅ Hit TP1 - ได้กำไรตามเป้า")

    print(f"{'─'*70}")

# Summary statistics
print(f"\n{'='*70}")
print(f"SUMMARY")
print(f"{'='*70}\n")

avg_rr = sum(abs(t['tp1'] - t['entry']) / abs(t['entry'] - t['sl'])
             for t in a3_trades if abs(t['entry'] - t['sl']) > 0) / len(a3_trades)

avg_sl_distance = sum(abs(t['entry'] - t['sl']) for t in a3_trades) / len(a3_trades)
avg_tp_distance = sum(abs(t['tp1'] - t['entry']) for t in a3_trades) / len(a3_trades)

print(f"Average R:R ratio: 1:{avg_rr:.2f}")
print(f"Average SL distance: ${avg_sl_distance:.2f}")
print(f"Average TP distance: ${avg_tp_distance:.2f}")

# Close reasons
close_reasons = {}
for t in a3_trades:
    reason = t['close_reason']
    close_reasons[reason] = close_reasons.get(reason, 0) + 1

print(f"\nClose Reasons:")
for reason, count in sorted(close_reasons.items(), key=lambda x: x[1], reverse=True):
    pct = (count / len(a3_trades)) * 100
    print(f"   {reason}: {count} ({pct:.1f}%)")

# RSI distribution
rsi_zones = {}
for t in a3_trades:
    zone = t['rsi_zone']
    rsi_zones[zone] = rsi_zones.get(zone, 0) + 1

print(f"\nRSI Zones:")
for zone, count in sorted(rsi_zones.items(), key=lambda x: x[1], reverse=True):
    pct = (count / len(a3_trades)) * 100
    print(f"   {zone}: {count} ({pct:.1f}%)")

print(f"\n{'='*70}\n")
