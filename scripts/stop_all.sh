#!/bin/bash
# หยุดทุก simulator/daemon ที่กำลังรันอยู่

cd "$(dirname "$0")/.." || exit 1

echo "=========================================="
echo "🛑 Stopping all Tra(i)der processes"
echo "=========================================="
echo ""

STOPPED=0

# หยุด daemon
if [ -f "traider_daemon.pid" ]; then
    DAEMON_PID=$(cat traider_daemon.pid)
    if ps -p "$DAEMON_PID" > /dev/null 2>&1; then
        echo "🛑 Stopping daemon (PID: $DAEMON_PID)..."
        kill "$DAEMON_PID"
        rm traider_daemon.pid
        STOPPED=$((STOPPED + 1))
    else
        echo "⚠️  Daemon PID file exists but process not found — cleaning up"
        rm traider_daemon.pid
    fi
fi

# หยุด simulator
if [ -f "traider.pid" ]; then
    SIM_PID=$(cat traider.pid)
    if ps -p "$SIM_PID" > /dev/null 2>&1; then
        echo "🛑 Stopping simulator (PID: $SIM_PID)..."
        kill "$SIM_PID"
        rm traider.pid
        STOPPED=$((STOPPED + 1))
    else
        echo "⚠️  Simulator PID file exists but process not found — cleaning up"
        rm traider.pid
    fi
fi

# หยุด background scripts
SCRIPT_PIDS=$(ps aux | grep -E "run_simulate.sh|run_winrate_test.sh|run_until_3am.sh" | grep -v grep | awk '{print $2}')
if [ -n "$SCRIPT_PIDS" ]; then
    echo "🛑 Stopping background scripts..."
    echo "$SCRIPT_PIDS" | xargs kill 2>/dev/null
    STOPPED=$((STOPPED + 1))
fi

# หยุด python processes (ระวัง — ใช้เฉพาะกรณีค้าง)
PYTHON_PIDS=$(ps aux | grep "python main.py" | grep -v grep | awk '{print $2}')
if [ -n "$PYTHON_PIDS" ]; then
    echo "⚠️  Found running Python processes:"
    echo "$PYTHON_PIDS"
    read -p "Kill these processes? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "$PYTHON_PIDS" | xargs kill 2>/dev/null
        STOPPED=$((STOPPED + 1))
    fi
fi

echo ""
if [ $STOPPED -eq 0 ]; then
    echo "✅ No processes running"
else
    echo "✅ Stopped $STOPPED process(es)"
fi

echo "=========================================="
