#!/bin/bash
# รัน Backtest mode

cd "$(dirname "$0")/.." || exit 1

# Default: backtest 14 วันย้อนหลัง
if [ -z "$1" ] || [ -z "$2" ]; then
    # คำนวณ 14 วันย้อนหลัง
    START_DATE=$(date -v-14d +%Y-%m-%d 2>/dev/null || date -d "14 days ago" +%Y-%m-%d)
    END_DATE=$(date +%Y-%m-%d)
    echo "📅 No dates specified — using last 14 days"
else
    START_DATE=$1
    END_DATE=$2
fi

LOG_FILE="logs/backtest_${START_DATE}_to_${END_DATE}_$(date +%H%M%S).log"

mkdir -p logs

echo "=========================================="
echo "📊 Tra(i)der Backtest"
echo "📅 Period: $START_DATE → $END_DATE"
echo "📝 Log: $LOG_FILE"
echo "=========================================="
echo ""

python main.py --backtest --start "$START_DATE" --end "$END_DATE" 2>&1 | tee "$LOG_FILE"

echo ""
echo "=========================================="
echo "✅ Backtest completed"
echo "📝 Full log: $LOG_FILE"
echo "=========================================="
