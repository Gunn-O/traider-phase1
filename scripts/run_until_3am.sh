#!/bin/bash
# รัน simulate mode จนถึงตี 3 ของวันพรุ่งนี้ (ก่อนตลาดปิด)

LOG_FILE="logs/simulate_$(date +%Y%m%d_%H%M%S).log"
mkdir -p logs

echo "=========================================="
echo "🚀 Starting Tra(i)der Simulator"
echo "⏰ Will run until tomorrow 03:00 AM (before market close)"
echo "📝 Log: $LOG_FILE"
echo "=========================================="

# คำนวณเวลาหยุด (ตี 3 ของวันพรุ่งนี้)
STOP_TIME=$(date -v+1d -j -f "%H:%M:%S" "03:00:00" +%s 2>/dev/null || \
            date -d "tomorrow 03:00:00" +%s)

echo "Stop time: $(date -r $STOP_TIME 2>/dev/null || date -d @$STOP_TIME)"
echo ""

# รัน loop
while true; do
    CURRENT_TIME=$(date +%s)

    if [ "$CURRENT_TIME" -ge "$STOP_TIME" ]; then
        echo ""
        echo "=========================================="
        echo "⏰ 03:00 AM reached — stopping simulator"
        echo "=========================================="
        break
    fi

    echo "--- $(date '+%Y-%m-%d %H:%M:%S') ---"
    python main.py --simulate --once 2>&1 | tee -a "$LOG_FILE"

    # รอ 5 นาที (300 วินาที) ก่อนรอบถัดไป
    echo "⏳ Waiting 5 minutes for next candle..."
    sleep 300
done

echo ""
echo "📊 Final Summary:"
grep -A 20 "SESSION SUMMARY" "$LOG_FILE" | tail -25
echo "Log saved: $LOG_FILE"
