#!/bin/bash
# รัน Winrate Test mode (lot 0.01 ทุกไม้, รันจนกว่าจะกด Ctrl+C)

cd "$(dirname "$0")/.." || exit 1

LOG_FILE="logs/winrate_test_$(date +%Y%m%d_%H%M%S).log"
PID_FILE="traider.pid"

mkdir -p logs

# ตรวจสอบว่ามี simulator รันอยู่แล้วหรือไม่
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "❌ Simulator already running (PID: $OLD_PID)"
        echo "   Stop it first: bash scripts/stop_all.sh"
        exit 1
    else
        rm "$PID_FILE"
    fi
fi

echo "=========================================="
echo "🧪 Tra(i)der Winrate Test"
echo "📊 Lot: 0.01 ทุกไม้"
echo "⏰ Will run until tomorrow 03:00 AM"
echo "📝 Log: $LOG_FILE"
echo "=========================================="
echo ""

# คำนวณเวลาหยุด (ตี 3 ของวันพรุ่งนี้)
STOP_TIME=$(date -v+1d -j -f "%H:%M:%S" "03:00:00" +%s 2>/dev/null || \
            date -d "tomorrow 03:00:00" +%s)

echo "Stop time: $(date -r $STOP_TIME 2>/dev/null || date -d @$STOP_TIME)"
echo ""

# บันทึก PID
echo $$ > "$PID_FILE"

while true; do
    CURRENT_TIME=$(date +%s)

    if [ "$CURRENT_TIME" -ge "$STOP_TIME" ]; then
        echo ""
        echo "=========================================="
        echo "⏰ 03:00 AM reached — stopping"
        echo "=========================================="
        rm "$PID_FILE"
        exit 0
    fi

    echo "--- $(date '+%Y-%m-%d %H:%M:%S') ---"
    python main.py --winrate-test --once 2>&1 | tee -a "$LOG_FILE"

    echo ""
    echo "⏳ Waiting 5 minutes..."
    echo ""
    sleep 300
done
