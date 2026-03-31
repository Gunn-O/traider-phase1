"""
Analyze Trade Frequency

ตรวจสอบว่า 46 trades ใน 7 วัน เยอะเกินไปหรือไม่
"""

import json
from datetime import datetime
from collections import defaultdict

# Load backtest results
with open('backtest/results/backtest_7days_claude.json', 'r') as f:
    results = json.load(f)

print("\n" + "="*70)
print("TRADE FREQUENCY ANALYSIS")
print("="*70)

trades = results['trades']
total_trades = len(trades)

print(f"\nTotal trades: {total_trades}")
print(f"Period: 7 days")
print(f"Average: {total_trades/7:.1f} trades/day")
print(f"\n{'='*70}\n")

# Group by day
trades_by_day = defaultdict(list)
for trade in trades:
    timestamp = datetime.fromisoformat(trade['timestamp'].replace('Z', '+00:00'))
    day = timestamp.date()
    trades_by_day[day].append(trade)

# Sort by date
sorted_days = sorted(trades_by_day.keys())

print("📅 Trades per Day:\n")
for day in sorted_days:
    day_trades = trades_by_day[day]
    count = len(day_trades)

    # Count by condition
    conditions = {}
    for t in day_trades:
        cond = t['condition']
        conditions[cond] = conditions.get(cond, 0) + 1

    print(f"{day.strftime('%Y-%m-%d (%a)')}: {count} trades")
    for cond, cnt in sorted(conditions.items(), key=lambda x: x[1], reverse=True):
        print(f"   {cond}: {cnt}")

# Time clustering analysis
print(f"\n{'='*70}")
print("⏰ Time Clustering Analysis")
print(f"{'='*70}\n")

# Sort trades by timestamp
sorted_trades = sorted(trades, key=lambda x: x['timestamp'])

# Find clusters (trades within 1 hour)
clusters = []
current_cluster = [sorted_trades[0]]

for i in range(1, len(sorted_trades)):
    prev_time = datetime.fromisoformat(sorted_trades[i-1]['timestamp'].replace('Z', '+00:00'))
    curr_time = datetime.fromisoformat(sorted_trades[i]['timestamp'].replace('Z', '+00:00'))

    time_diff = (curr_time - prev_time).total_seconds() / 60  # minutes

    if time_diff <= 60:  # Within 1 hour
        current_cluster.append(sorted_trades[i])
    else:
        if len(current_cluster) >= 3:  # Cluster with 3+ trades
            clusters.append(current_cluster)
        current_cluster = [sorted_trades[i]]

# Add last cluster if exists
if len(current_cluster) >= 3:
    clusters.append(current_cluster)

if clusters:
    print(f"Found {len(clusters)} clusters (3+ trades within 1 hour):\n")

    for i, cluster in enumerate(clusters, 1):
        start_time = datetime.fromisoformat(cluster[0]['timestamp'].replace('Z', '+00:00'))
        end_time = datetime.fromisoformat(cluster[-1]['timestamp'].replace('Z', '+00:00'))
        duration = (end_time - start_time).total_seconds() / 60

        print(f"Cluster #{i}: {len(cluster)} trades in {duration:.0f} minutes")
        print(f"   Time: {start_time.strftime('%Y-%m-%d %H:%M')} - {end_time.strftime('%H:%M')}")

        # Count conditions
        conditions = {}
        actions = {}
        results_count = {'WIN': 0, 'LOSS': 0}

        for t in cluster:
            conditions[t['condition']] = conditions.get(t['condition'], 0) + 1
            actions[t['action']] = actions.get(t['action'], 0) + 1
            if t['result'] in ['WIN', 'LOSS']:
                results_count[t['result']] += 1

        print(f"   Conditions: {dict(conditions)}")
        print(f"   Actions: {dict(actions)}")
        print(f"   Results: WIN {results_count['WIN']}, LOSS {results_count['LOSS']}")
        print()
else:
    print("No significant clusters found.")

# Rapid fire analysis (trades within 5 minutes)
print(f"{'='*70}")
print("🔥 Rapid Fire Trades (within 5 minutes)")
print(f"{'='*70}\n")

rapid_fire_count = 0
for i in range(1, len(sorted_trades)):
    prev_time = datetime.fromisoformat(sorted_trades[i-1]['timestamp'].replace('Z', '+00:00'))
    curr_time = datetime.fromisoformat(sorted_trades[i]['timestamp'].replace('Z', '+00:00'))

    time_diff = (curr_time - prev_time).total_seconds() / 60

    if time_diff <= 5:
        rapid_fire_count += 1
        print(f"   {prev_time.strftime('%Y-%m-%d %H:%M')} → {curr_time.strftime('%H:%M')}")
        print(f"      Gap: {time_diff:.1f} minutes")
        print(f"      {sorted_trades[i-1]['condition']} {sorted_trades[i-1]['action']} @ ${sorted_trades[i-1]['entry']:.2f}")
        print(f"      {sorted_trades[i]['condition']} {sorted_trades[i]['action']} @ ${sorted_trades[i]['entry']:.2f}")
        print()

if rapid_fire_count == 0:
    print("No rapid fire trades found.")
else:
    print(f"Total rapid fire sequences: {rapid_fire_count}")

# Recommendations
print(f"\n{'='*70}")
print("💡 RECOMMENDATIONS")
print(f"{'='*70}\n")

avg_per_day = total_trades / 7

if avg_per_day > 10:
    print(f"⚠️  {avg_per_day:.1f} trades/day is TOO HIGH")
    print(f"   Target: 3-7 trades/day (manual trading pace)")
    print(f"\n   Suggested fixes:")
    print(f"   1. Increase G2 confidence threshold (0.70 → 0.75+)")
    print(f"   2. Add cooldown period after SL hit (15-30 min)")
    print(f"   3. Tighten G1 filters (require stronger patterns)")
    print(f"   4. Block rapid re-entry on same condition")
elif avg_per_day >= 7:
    print(f"⚠️  {avg_per_day:.1f} trades/day is at upper limit")
    print(f"   Consider minor tightening of filters")
else:
    print(f"✓ {avg_per_day:.1f} trades/day is within acceptable range")

if len(clusters) > 0:
    print(f"\n⚠️  Found {len(clusters)} trade clusters - suggests overtrading")
    print(f"   Implement anti-clustering mechanism:")
    print(f"   - Max 2 trades per condition per hour")
    print(f"   - Cooldown after 2 consecutive losses")

print(f"\n{'='*70}\n")
