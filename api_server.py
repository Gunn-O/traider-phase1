"""
Web Dashboard API Server — FastAPI + WebSocket (v4.3)

หน้าที่:
- Serve dashboard UI (HTML single file)
- REST API endpoints สำหรับ control bot
- WebSocket สำหรับ real-time updates
- Shared state กับ main.py ผ่าน bot_state dict

V4.3 Updates:
- เพิ่ม proposals endpoint สำหรับ Monthly Evolver
- รองรับ beauty_score ใน bot_state

Target: Windows local machine (localhost only)
"""

import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ============================================================================
# SHARED STATE (in-memory)
# ============================================================================

# Global references (set by main.py)
sheets_logger = None
position_monitor = None

bot_state = {
    "status": "stopped",           # stopped / running / error
    "mode": "paper",               # paper / micro / live
    "symbol": "XAUUSDm",           # Trading symbol (XAUUSDm=Cent, XAUUSD=Real)
    "trading_tf": "M5",            # Selected timeframe
    "data_source_mode": "auto",    # V4.3: auto / mt5 / tv (user selected)
    "data_source_actual": "TradingView",  # V4.3: MT5 / TradingView (after connect)
    "current_price": 0.0,
    "active_plan_id": "",
    "open_orders": [],             # List of order dicts
    "daily_pnl": 0.0,
    "total_pnl": 0.0,
    "win": 0,
    "loss": 0,
    "consecutive_loss": 0,
    "last_decision": {},           # Claude decision ล่าสุด
    "last_reflection": "No history yet",  # Reflector summary
    "proposals": [],               # V4.3: Monthly Evolver proposals
    "agent_logs": {                # V4.3: Agent activity logs
        "analyst": [],
        "risk_manager": [],
        "weekly": [],
        "monthly": [],
        "reflector": [],
    },
    "latest_candle": {},           # V4.3: Latest OHLC for chart
    "logs": [],                    # List of log strings (max 50)
    "balance": 0.0,
    "last_updated": datetime.now().isoformat()
}

# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(
    title="XAUUSD Trading Bot Dashboard",
    description="Web dashboard for Tra(i)der Phase I v4.3 (4-Agent + Reflector)",
    version="4.3.0"
)

# Mount static files (for dashboard.html and assets)
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# ============================================================================
# WEBSOCKET MANAGER
# ============================================================================

class ConnectionManager:
    """Manage WebSocket connections for broadcasting bot_state"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected: {len(self.active_connections)} active")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected: {len(self.active_connections)} active")

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients"""
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to WebSocket: {e}")
                dead_connections.append(connection)

        # Remove dead connections
        for conn in dead_connections:
            self.disconnect(conn)


manager = ConnectionManager()


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class StartRequest(BaseModel):
    tf: str = "M5"           # Timeframe to trade
    symbol: str = "XAUUSDm"  # Symbol to trade (XAUUSDm=Cent, XAUUSD=Real)
    mode: str = "paper"      # Trading mode (paper/micro/live)
    data_source: str = "auto"  # Data source (auto/mt5/tv)


class StopRequest(BaseModel):
    reason: str = "User requested stop"


# ============================================================================
# REST API ENDPOINTS
# ============================================================================

@app.get("/")
async def serve_dashboard():
    """Serve dashboard HTML"""
    dashboard_path = static_dir / "dashboard.html"
    if not dashboard_path.exists():
        return HTMLResponse(
            content="<h1>Dashboard not found</h1><p>Create static/dashboard.html first</p>",
            status_code=404
        )
    return FileResponse(dashboard_path)


@app.get("/api/status")
async def get_status():
    """Get current bot status"""
    # Update timestamp
    bot_state["last_updated"] = datetime.now().isoformat()
    return bot_state


@app.post("/api/start")
async def start_bot(request: StartRequest):
    """
    Start bot with selected timeframe and symbol

    Args:
        request: {"tf": "M5", "symbol": "XAUUSDm"}

    Returns:
        {"status": "started", "tf": "M5", "symbol": "XAUUSDm"}
    """
    if bot_state["status"] == "running":
        raise HTTPException(status_code=400, detail="Bot already running")

    # Validate TF
    valid_tfs = ["M1", "M5", "M15", "M30", "H1", "H4"]
    if request.tf not in valid_tfs:
        raise HTTPException(status_code=400, detail=f"Invalid TF. Must be one of {valid_tfs}")

    # Validate Symbol
    valid_symbols = ["XAUUSDm", "XAUUSD"]
    if request.symbol not in valid_symbols:
        raise HTTPException(status_code=400, detail=f"Invalid symbol. Must be one of {valid_symbols}")

    # Validate Mode
    valid_modes = ["paper", "micro", "live"]
    if request.mode not in valid_modes:
        raise HTTPException(status_code=400, detail=f"Invalid mode. Must be one of {valid_modes}")

    # Validate Data Source
    valid_data_sources = ["auto", "mt5", "tv"]
    if request.data_source not in valid_data_sources:
        raise HTTPException(status_code=400, detail=f"Invalid data_source. Must be one of {valid_data_sources}")

    # Auto-set symbol based on mode (paper always uses XAUUSDm for price data)
    if request.mode == "paper":
        actual_symbol = "XAUUSDm"
    elif request.mode == "micro":
        actual_symbol = "XAUUSDm"
    else:  # live
        actual_symbol = "XAUUSD"

    # Update state
    bot_state["status"] = "running"
    bot_state["mode"] = request.mode
    bot_state["symbol"] = actual_symbol
    bot_state["trading_tf"] = request.tf
    bot_state["data_source_mode"] = request.data_source
    # data_source_actual will be updated by main.py after connector initialization

    mode_labels = {
        "paper": "Paper Trade (Simulate)",
        "micro": "Cent Account",
        "live": "Real Account"
    }
    mode_label = mode_labels.get(request.mode, request.mode)

    bot_state["logs"].append(
        f"{datetime.now().strftime('%H:%M:%S')} - Bot started "
        f"(Mode: {mode_label}, Symbol: {actual_symbol}, TF: {request.tf})"
    )
    bot_state["logs"] = bot_state["logs"][-50:]  # Keep last 50

    logger.info(f"Bot started with Mode: {request.mode}, Symbol: {actual_symbol}, TF: {request.tf}")

    # Broadcast to WebSocket clients
    await manager.broadcast({
        "event": "bot_started",
        "mode": request.mode,
        "tf": request.tf,
        "symbol": actual_symbol
    })

    return {
        "status": "started",
        "mode": request.mode,
        "tf": request.tf,
        "symbol": actual_symbol
    }


@app.post("/api/stop")
async def stop_bot(request: Optional[StopRequest] = None):
    """
    Stop bot gracefully (wait for current cycle to finish)

    Returns:
        {"status": "stopped"}
    """
    if bot_state["status"] != "running":
        raise HTTPException(status_code=400, detail="Bot not running")

    reason = request.reason if request else "User requested stop"

    # Update state
    bot_state["status"] = "stopped"
    bot_state["logs"].append(f"{datetime.now().strftime('%H:%M:%S')} - Bot stopped: {reason}")
    bot_state["logs"] = bot_state["logs"][-50:]

    logger.info(f"Bot stopped: {reason}")

    # Broadcast to WebSocket clients
    await manager.broadcast({"event": "bot_stopped", "reason": reason})

    return {"status": "stopped", "reason": reason}


@app.post("/api/emergency-stop")
async def emergency_stop():
    """
    Emergency stop — stop bot immediately + close all orders

    WARNING: This forcefully stops the bot and attempts to close all positions

    Returns:
        {"status": "emergency_stopped", "orders_closed": int}
    """
    # Update state
    bot_state["status"] = "stopped"
    bot_state["logs"].append(f"{datetime.now().strftime('%H:%M:%S')} - 🚨 EMERGENCY STOP")
    bot_state["logs"] = bot_state["logs"][-50:]

    # Count orders that were open
    orders_count = len(bot_state["open_orders"])

    # Clear open orders (in real implementation, this should trigger actual position close)
    # For now, just clear the state
    bot_state["open_orders"] = []
    bot_state["active_plan_id"] = ""

    logger.warning(f"Emergency stop triggered! {orders_count} orders cleared")

    # Broadcast to WebSocket clients
    await manager.broadcast({
        "event": "emergency_stop",
        "orders_closed": orders_count
    })

    return {"status": "emergency_stopped", "orders_closed": orders_count}


@app.get("/api/history")
async def get_history(limit: int = 30):
    """
    Get trade history (last N trades)
    Fetches from Google Sheets if available, otherwise fallback to in-memory

    Args:
        limit: Number of trades to return (default: 30)

    Returns:
        {
            "trades": [...],
            "source": "google_sheets" | "in_memory",
            "count": int
        }
    """
    # Try Google Sheets first
    try:
        if sheets_logger and sheets_logger.enabled:
            trades = sheets_logger.get_recent_trades(limit=limit)
            return {
                "trades": trades,
                "source": "google_sheets",
                "count": len(trades)
            }
    except Exception as e:
        logger.warning(f"Sheets unavailable: {e}")

    # Fallback: in-memory (PositionMonitor)
    try:
        if position_monitor:
            trades = position_monitor.get_closed_trades()[-limit:]
            return {
                "trades": trades,
                "source": "in_memory",
                "count": len(trades)
            }
    except Exception as e:
        logger.warning(f"PositionMonitor unavailable: {e}")

    # No data available
    return {
        "trades": [],
        "source": "none",
        "count": 0,
        "message": "No trade history available"
    }


@app.get("/api/proposals")
async def get_proposals():
    """
    Get Monthly Evolver proposals (V4.3)

    Returns:
        {
            "proposals": List[dict],  # Proposal objects from Monthly Evolver
            "count": int,
            "last_run": str           # ISO timestamp of last monthly analysis
        }
    """
    proposals = bot_state.get("proposals", [])
    return {
        "proposals": proposals,
        "count": len(proposals),
        "last_run": bot_state.get("last_monthly_run", "Never")
    }


@app.post("/api/proposals/clear")
async def clear_proposals():
    """
    Clear all proposals (after human review)

    Returns:
        {"status": "cleared", "count": int}
    """
    count = len(bot_state.get("proposals", []))
    bot_state["proposals"] = []
    bot_state["logs"].append(f"{datetime.now().strftime('%H:%M:%S')} - Proposals cleared ({count} items)")
    bot_state["logs"] = bot_state["logs"][-50:]

    logger.info(f"Cleared {count} proposals")

    # Broadcast to WebSocket clients
    await manager.broadcast({"event": "proposals_cleared", "count": count})

    return {"status": "cleared", "count": count}


@app.get("/api/agent-logs")
async def get_agent_logs():
    """
    Get all agent logs

    Returns:
        {
            "analyst": [...],
            "risk_manager": [...],
            "weekly": [...],
            "monthly": [...],
            "reflector": [...]
        }
    """
    return bot_state.get("agent_logs", {
        "analyst": [],
        "risk_manager": [],
        "weekly": [],
        "monthly": [],
        "reflector": [],
    })


@app.get("/api/agent-logs/{agent}")
async def get_agent_log(agent: str):
    """
    Get logs for specific agent

    Args:
        agent: analyst | risk_manager | weekly | monthly | reflector

    Returns:
        List of log entries for that agent
    """
    valid_agents = ["analyst", "risk_manager", "weekly", "monthly", "reflector"]
    if agent not in valid_agents:
        raise HTTPException(status_code=400, detail=f"Invalid agent. Must be one of {valid_agents}")

    return {
        "agent": agent,
        "logs": bot_state.get("agent_logs", {}).get(agent, []),
        "count": len(bot_state.get("agent_logs", {}).get(agent, []))
    }


@app.get("/api/agent-costs")
async def get_agent_costs():
    """
    Get cost summary for all agents

    Returns:
        {
            "analyst": {"total_cost": 0.412, "calls": 21, "model": "Sonnet"},
            ...
        }
    """
    agent_logs = bot_state.get("agent_logs", {})

    summary = {}
    for agent_name, logs in agent_logs.items():
        total_cost = sum(log.get("cost_usd", 0) for log in logs)
        calls = len(logs)
        model = logs[0].get("model", "Unknown") if logs else "Unknown"

        summary[agent_name] = {
            "total_cost": round(total_cost, 3),
            "calls": calls,
            "model": model,
            "avg_cost": round(total_cost / calls, 4) if calls > 0 else 0,
        }

    return summary


@app.get("/api/candles")
async def get_candles(tf: str = "M5", count: int = 100):
    """
    Get latest OHLC candles for chart

    Args:
        tf: Timeframe (M1/M5/M15/M30/H1/H4)
        count: Number of candles (default: 100)

    Returns:
        {
            "candles": [...],
            "tf": "M5",
            "symbol": "XAUUSDm"
        }
    """
    # TODO: Integration with data connector
    # For now, return empty or mock data
    return {
        "candles": [],
        "tf": tf,
        "symbol": bot_state.get("symbol", "XAUUSDm"),
        "message": "Candles endpoint — requires connector integration"
    }


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "bot_status": bot_state["status"]
    }


# ============================================================================
# WEBSOCKET ENDPOINT
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time bot_state updates

    Broadcasts bot_state every 1 second to all connected clients
    """
    await manager.connect(websocket)

    try:
        while True:
            # Send current bot_state
            await websocket.send_json(bot_state)

            # Wait 1 second
            await asyncio.sleep(1.0)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# ============================================================================
# STARTUP / SHUTDOWN EVENTS
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
    logger.info("🚀 API Server starting...")
    logger.info("📊 Dashboard available at http://127.0.0.1:8080")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("🛑 API Server shutting down...")


# ============================================================================
# HELPER FUNCTIONS (called from main.py)
# ============================================================================

def update_bot_state(updates: Dict):
    """
    Update bot_state from main.py

    Usage:
        from api_server import update_bot_state
        update_bot_state({"current_price": 3245.50, "status": "running"})

    Args:
        updates: Dict of key-value pairs to update in bot_state
    """
    for key, value in updates.items():
        if key in bot_state:
            bot_state[key] = value
    bot_state["last_updated"] = datetime.now().isoformat()


def add_log(message: str):
    """
    Add log entry to bot_state

    Usage:
        from api_server import add_log
        add_log("G2 BLOCK: unclear chart")

    Args:
        message: Log message (will be prepended with timestamp)
    """
    timestamp = datetime.now().strftime('%H:%M:%S')
    bot_state["logs"].append(f"{timestamp} - {message}")
    bot_state["logs"] = bot_state["logs"][-50:]  # Keep last 50


def get_bot_status() -> str:
    """
    Get current bot status

    Returns:
        "stopped" | "running" | "error"
    """
    return bot_state["status"]


def set_sheets_logger(logger_instance):
    """
    Set SheetsLogger instance for /api/history endpoint

    Usage:
        from api_server import set_sheets_logger
        set_sheets_logger(sheets_logger)
    """
    global sheets_logger
    sheets_logger = logger_instance


def set_position_monitor(monitor_instance):
    """
    Set PositionMonitor instance for /api/history fallback

    Usage:
        from api_server import set_position_monitor
        set_position_monitor(position_monitor)
    """
    global position_monitor
    position_monitor = monitor_instance


def add_agent_log(agent: str, log_entry: Dict):
    """
    Add log entry for specific agent

    Usage:
        from api_server import add_agent_log
        add_agent_log("analyst", {
            "timestamp": "2026-04-21 08:32:15",
            "action": "BUY",
            "reason": "uptrend+twin_candle",
            "cost_usd": 0.0197,
            "tokens": {...},
            "latency_sec": 2.3,
            "model": "claude-sonnet-4-20250514"
        })

    Args:
        agent: analyst | risk_manager | weekly | monthly | reflector
        log_entry: Log dict
    """
    valid_agents = ["analyst", "risk_manager", "weekly", "monthly", "reflector"]
    if agent not in valid_agents:
        logger.warning(f"Invalid agent: {agent}")
        return

    if "agent_logs" not in bot_state:
        bot_state["agent_logs"] = {a: [] for a in valid_agents}

    bot_state["agent_logs"][agent].append(log_entry)
    # Keep last 50 entries per agent
    bot_state["agent_logs"][agent] = bot_state["agent_logs"][agent][-50:]


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    print("="*70)
    print("🚀 Starting XAUUSD Bot Dashboard API Server")
    print("="*70)
    print("📊 Dashboard: http://127.0.0.1:8080")
    print("📡 API Docs:  http://127.0.0.1:8080/docs")
    print("🔌 WebSocket: ws://127.0.0.1:8080/ws")
    print("="*70)

    uvicorn.run(
        app,
        host="127.0.0.1",  # localhost only — DO NOT change to 0.0.0.0
        port=8080,
        log_level="info"
    )
