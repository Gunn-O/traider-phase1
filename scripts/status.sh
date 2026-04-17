#!/bin/bash
# ดูสถานะ simulator/daemon ที่กำลังรันอยู่

cd "$(dirname "$0")/.." || exit 1

echo "=========================================="
echo "📊 Tra(i)der Status"
echo "=========================================="
echo ""

RUNNING=0

# เช็ค daemon
if [ -f "traider_daemon.pid" ]; then
    DAEMON_PID=$(cat traider_daemon.pid)
    if ps -p "$DAEMON_PID" > /dev/null 2>&1; then
        echo "🟢 Daemon running (PID: $DAEMON_PID)"
        DAEMON_LOG=$(ls -t logs/simulate_daemon_*.log 2>/dev/null | head -1)
        if [ -n "$DAEMON_LOG" ]; then
            echo "   Log: $DAEMON_LOG"
            CYCLES=$(grep -c "Starting trading cycle" "$DAEMON_LOG" 2>/dev/null || echo 0)
            echo "   Cycles: $CYCLES"
            LAST_SKIP=$(grep "SKIP:" "$DAEMON_LOG" | tail -1 | sed 's/.*SKIP: //')
            if [ -n "$LAST_SKIP" ]; then
                echo "   Last: SKIP - $LAST_SKIP"
            fi
        fi
        RUNNING=$((RUNNING + 1))
        echo ""
    else
        echo "⚠️  Daemon PID file exists but process not running"
        echo ""
    fi
fi

# เช็ค simulator
if [ -f "traider.pid" ]; then
    SIM_PID=$(cat traider.pid)
    if ps -p "$SIM_PID" > /dev/null 2>&1; then
        echo "🟢 Simulator running (PID: $SIM_PID)"
        SIM_LOG=$(ls -t logs/simulate_*.log 2>/dev/null | head -1)
        if [ -n "$SIM_LOG" ]; then
            echo "   Log: $SIM_LOG"
            CYCLES=$(grep -c "Starting trading cycle" "$SIM_LOG" 2>/dev/null || echo 0)
            echo "   Cycles: $CYCLES"
            LAST_SKIP=$(grep "SKIP:" "$SIM_LOG" | tail -1 | sed 's/.*SKIP: //')
            if [ -n "$LAST_SKIP" ]; then
                echo "   Last: SKIP - $LAST_SKIP"
            fi
        fi
        RUNNING=$((RUNNING + 1))
        echo ""
    else
        echo "⚠️  Simulator PID file exists but process not running"
        echo ""
    fi
fi

# เช็ค background scripts
SCRIPT_PIDS=$(ps aux | grep -E "run_simulate.sh|run_winrate_test.sh|run_until_3am.sh" | grep -v grep | awk '{print $2}')
if [ -n "$SCRIPT_PIDS" ]; then
    echo "🟢 Background scripts running:"
    ps aux | grep -E "run_simulate.sh|run_winrate_test.sh|run_until_3am.sh" | grep -v grep | awk '{print "   PID:", $2, "—", $11, $12, $13}'
    RUNNING=$((RUNNING + 1))
    echo ""
fi

# เช็ค Google Sheets
echo "📊 Google Sheets:"
python -c "
from agents.g4_sheets_logger import SheetsLogger
logger = SheetsLogger()
trade_log = logger.trade_log_ws.get_all_records()
state = logger.get_portfolio_state()
print(f'   Trade Log: {len(trade_log)} rows')
print(f'   Active Plan: {state.get(\"active_plan_id\")}')
print(f'   Open Orders: {state.get(\"open_orders_count\")}')
print(f'   Trading Blocked: {state.get(\"trading_blocked\")}')
" 2>/dev/null || echo "   ⚠️  Cannot connect to Sheets"

echo ""
echo "=========================================="
if [ $RUNNING -eq 0 ]; then
    echo "❌ No processes running"
    echo ""
    echo "Start simulator:"
    echo "  bash scripts/run_simulate.sh"
    echo "  bash scripts/run_winrate_test.sh"
    echo "  bash scripts/run_daemon.sh"
else
    echo "✅ $RUNNING process(es) running"
fi
echo "=========================================="
