#!/bin/bash
# Script สำหรับเช็คผลลัพธ์ backtest

echo "=== Checking Backtest Status ==="
echo ""

# Check if process is running
if ps aux | grep -q "[b]acktest_7days.py"; then
    echo "✓ Backtest is still RUNNING"
    echo ""

    # Try to find recent output
    echo "Recent logs (if any):"
    find /private/tmp -name "*.output" -type f -mmin -30 2>/dev/null | while read f; do
        if [ -s "$f" ]; then
            echo "Found: $f"
            echo "Last 20 lines:"
            tail -20 "$f"
        fi
    done
else
    echo "✓ Backtest has FINISHED or not running"
fi

echo ""
echo "=== Saved Results ==="

# Check for JSON results
if [ -f "backtest/results/backtest_7days_claude.json" ]; then
    echo "✓ Found JSON results: backtest/results/backtest_7days_claude.json"

    # Quick summary from JSON
    python3 << 'EOF'
import json
try:
    with open('backtest/results/backtest_7days_claude.json', 'r') as f:
        data = json.load(f)

    total = data.get('guardian_approved', 0)
    wins = data.get('win_count', 0)
    losses = data.get('loss_count', 0)
    pnl = data.get('total_pnl', 0)

    if total > 0:
        win_rate = (wins / total) * 100
        print(f"\n📊 Quick Summary:")
        print(f"   Total Trades: {total}")
        print(f"   Wins: {wins} ({win_rate:.1f}%)")
        print(f"   Losses: {losses}")
        print(f"   Total P&L: ${pnl:,.2f}")
    else:
        print("   No trades yet")
except Exception as e:
    print(f"   Error reading JSON: {e}")
EOF
else
    echo "⏳ JSON results not yet saved"
fi

echo ""
echo "=== How to View Results ==="
echo "1. Wait for backtest to finish"
echo "2. Results will be saved to: backtest/results/backtest_7days_claude.json"
echo "3. Or re-run: python backtest_7days.py"
echo ""
