#!/bin/bash
# รัน simulator แบบ daemon (ทำงานต่อแม้ปิดเครื่อง)

cd "$(dirname "$0")/.." || exit 1

LOG_FILE="logs/simulate_daemon_$(date +%Y%m%d_%H%M%S).log"
PID_FILE="traider_daemon.pid"

mkdir -p logs

# ตรวจสอบว่ามี daemon รันอยู่แล้วหรือไม่
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "❌ Simulator daemon already running (PID: $OLD_PID)"
        echo "   Stop it first: kill $OLD_PID"
        exit 1
    else
        # PID file เก่า แต่ process ตายแล้ว
        rm "$PID_FILE"
    fi
fi

echo "=========================================="
echo "🚀 Starting Tra(i)der Daemon"
echo "⏰ Will run until tomorrow 03:00 AM"
echo "📝 Log: $LOG_FILE"
echo "=========================================="

# คำนวณเวลาหยุด (ตี 3 ของวันพรุ่งนี้)
STOP_TIME=$(date -v+1d -j -f "%H:%M:%S" "03:00:00" +%s 2>/dev/null || \
            date -d "tomorrow 03:00:00" +%s)

echo "Stop time: $(date -r $STOP_TIME 2>/dev/null || date -d @$STOP_TIME)"

# รันด้วย nohup (ไม่ถูก kill เมื่อ terminal ปิด)
nohup bash -c '
STOP_TIME='"$STOP_TIME"'
LOG_FILE="'"$LOG_FILE"'"

while true; do
    CURRENT_TIME=$(date +%s)

    if [ "$CURRENT_TIME" -ge "$STOP_TIME" ]; then
        echo "" >> "$LOG_FILE"
        echo "==========================================" >> "$LOG_FILE"
        echo "⏰ 03:00 AM reached — stopping daemon" >> "$LOG_FILE"
        echo "==========================================" >> "$LOG_FILE"
        break
    fi

    echo "--- $(date "+%Y-%m-%d %H:%M:%S") ---" >> "$LOG_FILE"
    python main.py --simulate --once >> "$LOG_FILE" 2>&1

    echo "⏳ Waiting 5 minutes..." >> "$LOG_FILE"
    sleep 300
done

# Session summary
echo "" >> "$LOG_FILE"
echo "📊 Final Summary:" >> "$LOG_FILE"
grep -A 20 "SESSION SUMMARY" "$LOG_FILE" | tail -25 >> "$LOG_FILE"
echo "Daemon stopped at $(date)" >> "$LOG_FILE"
' > /dev/null 2>&1 &

# บันทึก PID
DAEMON_PID=$!
echo $DAEMON_PID > "$PID_FILE"

echo ""
echo "✅ Daemon started (PID: $DAEMON_PID)"
echo "   Log: $LOG_FILE"
echo "   PID file: $PID_FILE"
echo ""
echo "Commands:"
echo "  Check status:  ps -p $DAEMON_PID"
echo "  View log:      tail -f $LOG_FILE"
echo "  Stop daemon:   kill $DAEMON_PID"
echo "                 rm $PID_FILE"
echo ""
echo "ปิดหน้าจอได้เลย — daemon จะรันต่อในพื้นหลัง 🚀"
