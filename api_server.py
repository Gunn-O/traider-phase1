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
import json
import logging
import os
import subprocess
import threading
import sys
from collections import deque
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path
from dotenv import load_dotenv

# ─── Multi-bot session persistence ───────────────────────────────────
# Array of {tf, symbol, mode, data_source} for every bot currently running.
# Updated whenever a bot starts/stops; read by launcher on boot to auto-resume.
SESSIONS_FILE = Path(__file__).resolve().parent / "last_sessions.json"


def _save_sessions() -> None:
    """Persist configs of currently-running bots so launcher can resume after reboot."""
    sessions = [
        {"tf": b["tf"], "symbol": b["symbol"], "mode": b["mode"], "data_source": b["data_source"]}
        for b in bots.values() if b["status"] == "running"
    ]
    try:
        if sessions:
            SESSIONS_FILE.write_text(json.dumps(sessions))
        else:
            SESSIONS_FILE.unlink(missing_ok=True)
    except Exception as e:
        logger.warning(f"Failed to write last_sessions.json: {e}")


# ─── Multi-bot state ─────────────────────────────────────────────────
# bot_id format: "{tf}-{symbol}-{mode}" — uniquely identifies a config.
# Two bots with the same id can't coexist (start would 400).
bots: Dict[str, dict] = {}
_bot_procs: Dict[str, subprocess.Popen] = {}


def _make_bot_id(tf: str, symbol: str, mode: str) -> str:
    return f"{tf}-{symbol}-{mode}"


def _new_bot_state(req: "StartRequest", pid: int) -> dict:
    now = datetime.now().isoformat()
    return {
        "bot_id": _make_bot_id(req.tf, req.symbol, req.mode),
        "tf": req.tf,
        "symbol": req.symbol,
        "mode": req.mode,
        "data_source": req.data_source,
        "status": "running",
        "bot_pid": pid,
        "started_at": now,
        "last_updated": now,
        "open_orders": [],     # populated via POST /api/bots/{id}/event
        "closed_orders": [],   # ring buffer of last 50 closed orders
        "events": deque(maxlen=200),
        "balance": float(os.getenv("ACCOUNT_BALANCE", "1000")),
        # Per-cycle snapshot pushed by main.py via POST /api/bots/{id}/heartbeat.
        # Lives outside `events` so a 60s cycle tick doesn't flood the panel.
        # Always overwrites the previous snapshot — only the latest tick matters.
        "heartbeat": {},
        "cycle_count": 0,
    }


def _serialize_bot(b: dict) -> dict:
    """Convert deque → list so JSON encoder accepts it."""
    return {**b, "events": list(b["events"])}


def _add_event(bot_id: str, ev_type: str, msg: str = "", data: Optional[dict] = None) -> None:
    if bot_id not in bots:
        return
    bots[bot_id]["events"].append({
        "ts": datetime.now().isoformat(),
        "type": ev_type,
        "msg": msg,
        "data": data or {},
    })
    bots[bot_id]["last_updated"] = datetime.now().isoformat()


def _hydrate_bot_from_db(bot_id: str, db_path: str = "traider_sim.db") -> None:
    """Replace bots[bot_id]['open_orders'] + ['closed_orders'] with whatever
    LocalDB shows for this bot_id right now. Called on /api/start and also
    exposed via POST /api/bots/{id}/sync so the UI can be refreshed after
    `reconcile_pending.py` without having to restart anything.

    Best-effort: any DB error is swallowed (returns with the in-memory state
    untouched). Trades older than `MAX_CLOSED_LOOKBACK` are not loaded so the
    Dashboard's "Recently Closed" panel stays focused on recent activity."""
    if bot_id not in bots:
        return
    if not os.path.exists(db_path):
        return
    try:
        import sqlite3
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        # Open = anything still PENDING for this bot. Include chart_type +
        # timestamp_open so the Dashboard Open Positions panel can render the
        # Strategy column and Time column without having to wait for the next
        # event broadcast.
        open_rows = con.execute(
            "SELECT trade_id, plan_id, action, entry_price, sl_price, tp_price, "
            "lot_size, rr_ratio, chart_type, timestamp_open FROM trades "
            "WHERE bot_id = ? AND result = 'PENDING' "
            "ORDER BY timestamp_open",
            (bot_id,),
        ).fetchall()
        bots[bot_id]["open_orders"] = [
            {
                "plan_id":   r["plan_id"],
                "trade_id":  r["trade_id"],
                "action":    r["action"],
                "entry":     r["entry_price"],
                "sl":        r["sl_price"],
                "tp":        r["tp_price"],
                "lot":       r["lot_size"],
                "lot_size":  r["lot_size"],
                "rr":        r["rr_ratio"],
                "pattern":   (r["chart_type"] or "").upper(),
                "open_time": r["timestamp_open"],
            }
            for r in open_rows
        ]
        # Closed = last 50 WIN/LOSS/CANCELLED for this bot, newest last.
        # Pull entry / SL / TP / lot too — Dashboard's unified Positions
        # panel renders the same 12 columns for OPEN and CLOSED rows, so
        # closed rows need the entry levels to populate Entry/SL/TP/Lot.
        # Previously those columns were blank for any trade loaded from DB.
        closed_rows = con.execute(
            "SELECT trade_id, plan_id, action, entry_price, sl_price, tp_price, "
            "lot_size, rr_ratio, result, close_reason, close_price, pnl_usd, "
            "timestamp_close, chart_type, timestamp_open FROM trades "
            "WHERE bot_id = ? AND result IN ('WIN','LOSS','CANCELLED') "
            "ORDER BY timestamp_close ASC LIMIT 50",
            (bot_id,),
        ).fetchall()
        bots[bot_id]["closed_orders"] = [
            {
                "plan_id":      r["plan_id"],
                "trade_id":     r["trade_id"],
                "action":       r["action"],
                "entry":        r["entry_price"],
                "sl":           r["sl_price"],
                "tp":           r["tp_price"],
                "lot":          r["lot_size"],
                "lot_size":     r["lot_size"],
                "rr":           r["rr_ratio"],
                "result":       r["result"],
                "close_reason": r["close_reason"],
                "close_price":  r["close_price"],
                "pnl":          r["pnl_usd"],
                "close_time":   r["timestamp_close"],
                "pattern":      (r["chart_type"] or "").upper(),
                "open_time":    r["timestamp_open"],
            }
            for r in closed_rows
        ]
        con.close()
        logger.info(
            f"Hydrated {bot_id} from DB: "
            f"open={len(bots[bot_id]['open_orders'])} "
            f"closed={len(bots[bot_id]['closed_orders'])}"
        )
    except Exception as e:
        logger.warning(f"_hydrate_bot_from_db({bot_id}): {e}")


def _sweep_dead() -> List[str]:
    """Detect bot subprocesses that exited; flip their status to 'stopped'.
    Returns the list of bot_ids that just transitioned."""
    transitioned = []
    for bot_id, proc in list(_bot_procs.items()):
        rc = proc.poll()
        if rc is not None:
            if bot_id in bots and bots[bot_id]["status"] == "running":
                bots[bot_id]["status"] = "stopped"
                bots[bot_id]["bot_pid"] = None
                _add_event(bot_id, "subprocess_died", f"exit code {rc}", {"rc": rc})
                transitioned.append(bot_id)
            _bot_procs.pop(bot_id, None)
    if transitioned:
        _save_sessions()
    return transitioned

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# ============================================================================
# SHARED STATE (in-memory)
# ============================================================================

# Global references (set by main.py)
sheets_logger = None
position_monitor = None
connector = None

# ── Global backtest state ──────────────────────────
_backtest_state = {
    "is_running": False,
    "start": None,
    "end": None,
    "error": None,
    "pid": None,
}

def _run_backtest_thread(start: str, end: str, timeframe: str = "M5"):
    """รัน backtest ใน background thread"""
    global _backtest_state
    try:
        _backtest_state["is_running"] = True
        _backtest_state["error"] = None
        _backtest_state["timeframe"] = timeframe

        # หา project root (ที่มี main.py)
        project_root = Path(__file__).parent
        python_exe   = sys.executable  # ใช้ python เดิมที่รัน api_server

        cmd = [
            python_exe, "main.py",
            "--backtest",
            "--start", start,
            "--end",   end,
            "--decision-engine", "python"
        ]

        # Pass BACKTEST_TIMEFRAME via env to subprocess
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["BACKTEST_TIMEFRAME"] = timeframe

        # Hide console window when launched from .exe launcher (Windows)
        creationflags = 0
        startupinfo = None
        if sys.platform == 'win32':
            creationflags = subprocess.CREATE_NO_WINDOW
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE

        proc = subprocess.Popen(
            cmd,
            cwd=str(project_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            creationflags=creationflags,
            startupinfo=startupinfo,
        )
        _backtest_state["pid"] = proc.pid

        # Stream output ไป log
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                logger.info(f"[BACKTEST] {line}")

        proc.wait()

        if proc.returncode != 0:
            _backtest_state["error"] = f"Exit code {proc.returncode}"
            logger.error(f"Backtest failed: exit {proc.returncode}")

    except Exception as e:
        _backtest_state["error"] = str(e)
        logger.error(f"Backtest thread error: {e}")
    finally:
        _backtest_state["is_running"] = False
        _backtest_state["pid"] = None
        logger.info("✅ Backtest thread finished")

bot_state = {
    "status": "stopped",           # stopped / running / error
    "mode": "paper",               # paper / micro / live
    "symbol": "XAUUSDc",           # Trading symbol (XAUUSDc=Cent, XAUUSD=Real)
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
    "balance": float(os.getenv("ACCOUNT_BALANCE", "10000")),  # อ่านจาก .env
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

# CORS middleware (allow frontend on localhost:3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    symbol: str = "XAUUSDc"  # Symbol to trade (XAUUSDc=Cent, XAUUSD=Real)
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


# ─── Multi-bot endpoints ────────────────────────────────────────────

class BotEvent(BaseModel):
    type: str
    msg: str = ""
    data: dict = {}


@app.get("/api/bots")
async def list_bots():
    """List all bots (running + recently stopped) with their state and event count."""
    _sweep_dead()
    return {
        "bots": [_serialize_bot(b) for b in bots.values()],
        "count": len(bots),
        "running": sum(1 for b in bots.values() if b["status"] == "running"),
    }


@app.get("/api/bots/{bot_id}")
async def get_bot(bot_id: str):
    _sweep_dead()
    if bot_id not in bots:
        raise HTTPException(status_code=404, detail=f"Bot {bot_id} not found")
    return _serialize_bot(bots[bot_id])


@app.post("/api/bots/{bot_id}/event")
async def post_bot_event(bot_id: str, event: BotEvent):
    """Bot subprocess (main.py) POSTs significant events here so the UI sees them.
    Some types also mutate bot state (open_orders, closed_orders)."""
    if bot_id not in bots:
        raise HTTPException(status_code=404, detail=f"Bot {bot_id} not found")

    _add_event(bot_id, event.type, event.msg, event.data)

    if event.type == "plan_opened":
        bots[bot_id]["open_orders"].append(event.data)
    elif event.type == "plan_closed":
        plan_id = event.data.get("plan_id")
        bots[bot_id]["open_orders"] = [
            o for o in bots[bot_id]["open_orders"] if o.get("plan_id") != plan_id
        ]
        closed = bots[bot_id].setdefault("closed_orders", [])
        closed.append(event.data)
        bots[bot_id]["closed_orders"] = closed[-50:]

    await manager.broadcast({
        "event": "bot_event",
        "bot_id": bot_id,
        "data": {"ts": datetime.now().isoformat(), **event.dict()},
    })
    return {"ok": True}


@app.post("/api/bots/{bot_id}/sync")
async def sync_bot_from_db(bot_id: str):
    """Reload open_orders + closed_orders for a bot directly from LocalDB.
    Useful right after `scripts/reconcile_pending.py` runs while the bot is
    stopped — the Dashboard then reflects the new state without having to
    restart anything. Also broadcasts so connected UIs refresh immediately."""
    if bot_id not in bots:
        raise HTTPException(status_code=404, detail=f"Bot {bot_id} not found")
    _hydrate_bot_from_db(bot_id)
    await manager.broadcast({
        "event": "bot_synced",
        "bot_id": bot_id,
        "bot": _serialize_bot(bots[bot_id]),
    })
    return {
        "ok": True,
        "bot_id": bot_id,
        "open": len(bots[bot_id]["open_orders"]),
        "closed": len(bots[bot_id]["closed_orders"]),
    }


@app.post("/api/bots/{bot_id}/heartbeat")
async def post_bot_heartbeat(bot_id: str, request: Request):
    """Bot subprocess (main.py) POSTs a per-cycle snapshot here so the UI can
    show 'system is alive' updates (last candle, current price, R55, session,
    skip reason). Stored in bots[bot_id]['heartbeat'] — overwrites previous;
    NOT appended to the events deque (would flood it at 60s cadence)."""
    if bot_id not in bots:
        raise HTTPException(status_code=404, detail=f"Bot {bot_id} not found")
    body = await request.json()
    now_iso = datetime.now().isoformat()
    bots[bot_id]["heartbeat"] = {**body, "ts": now_iso}
    bots[bot_id]["cycle_count"] = bots[bot_id].get("cycle_count", 0) + 1
    bots[bot_id]["last_updated"] = now_iso
    await manager.broadcast({
        "event": "bot_heartbeat",
        "bot_id": bot_id,
        "data": bots[bot_id]["heartbeat"],
        "cycle_count": bots[bot_id]["cycle_count"],
    })
    return {"ok": True}


@app.get("/api/bots/{bot_id}/events")
async def get_bot_events(bot_id: str, limit: int = 50, type: Optional[str] = None):
    if bot_id not in bots:
        raise HTTPException(status_code=404, detail=f"Bot {bot_id} not found")
    events = list(bots[bot_id]["events"])
    if type:
        events = [e for e in events if e["type"] == type]
    return {"events": events[-limit:], "total": len(bots[bot_id]["events"])}


@app.get("/api/status")
async def get_status():
    """Legacy aggregate status — mirrors the first running bot for backward compat
    with non-Dashboard pages. New code should use /api/bots instead."""
    _sweep_dead()
    running = [b for b in bots.values() if b["status"] == "running"]
    bot_state["status"] = "running" if running else "stopped"
    if running:
        first = running[0]
        bot_state["mode"] = first["mode"]
        bot_state["symbol"] = first["symbol"]
        bot_state["trading_tf"] = first["tf"]
        bot_state["data_source_mode"] = first["data_source"]
        bot_state["bot_pid"] = first["bot_pid"]
        bot_state["open_orders"] = first["open_orders"]
    else:
        bot_state["bot_pid"] = None
        bot_state["open_orders"] = []
    bot_state["last_updated"] = datetime.now().isoformat()
    return bot_state


@app.post("/api/start")
async def start_bot(request: StartRequest):
    """Start a bot for the given (tf, symbol, mode). Multiple bots may run concurrently
    as long as their (tf, symbol, mode) tuple differs. Returns the bot_id."""
    valid_tfs = ["M1", "M5", "M15", "M30", "H1", "H4"]
    valid_symbols = ["XAUUSDc", "XAUUSDm", "XAUUSD"]
    valid_modes = ["paper", "micro", "live"]
    valid_data_sources = ["auto", "mt5", "yf", "tv"]
    if request.tf not in valid_tfs:
        raise HTTPException(status_code=400, detail=f"Invalid TF. Must be one of {valid_tfs}")
    if request.symbol not in valid_symbols:
        raise HTTPException(status_code=400, detail=f"Invalid symbol. Must be one of {valid_symbols}")
    if request.mode not in valid_modes:
        raise HTTPException(status_code=400, detail=f"Invalid mode. Must be one of {valid_modes}")
    if request.data_source not in valid_data_sources:
        raise HTTPException(status_code=400, detail=f"Invalid data_source. Must be one of {valid_data_sources}")

    _sweep_dead()
    bot_id = _make_bot_id(request.tf, request.symbol, request.mode)
    if bot_id in bots and bots[bot_id]["status"] == "running":
        raise HTTPException(status_code=400, detail=f"Bot {bot_id} already running")

    project_root = Path(__file__).parent
    cmd = [
        sys.executable, str(project_root / "main.py"),
        "--simulate",
        "--mode", request.mode,
        "--symbol", request.symbol,
        "--tf", request.tf,
        "--data-source", request.data_source,
        "--no-confirm",
        "--decision-engine", "python",
    ]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["BACKTEST_TIMEFRAME"] = request.tf
    env["TRAIDER_BOT_ID"] = bot_id            # subprocess uses this to label events
    env["TRAIDER_API_URL"] = f"http://127.0.0.1:8080"

    creationflags = 0
    startupinfo = None
    if sys.platform == 'win32':
        creationflags = subprocess.CREATE_NO_WINDOW
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0

    try:
        proc = subprocess.Popen(
            cmd, cwd=str(project_root), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=creationflags, startupinfo=startupinfo,
        )
    except Exception as e:
        logger.error(f"Failed to spawn bot subprocess for {bot_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start bot: {e}")

    bots[bot_id] = _new_bot_state(request, proc.pid)
    # Pre-populate open_orders + closed_orders from LocalDB so the Dashboard
    # immediately shows history that lives in the DB but not in api_server's
    # in-memory ring buffer (e.g. after an api_server restart, or after
    # `scripts/reconcile_pending.py` adjusts trades while the bot was stopped).
    _hydrate_bot_from_db(bot_id)
    _bot_procs[bot_id] = proc
    _add_event(bot_id, "started", f"Bot {bot_id} started (pid={proc.pid})")
    _save_sessions()
    logger.info(f"Bot {bot_id} subprocess spawned: pid={proc.pid}")

    await manager.broadcast({
        "event": "bot_started",
        "bot_id": bot_id,
        "bot": _serialize_bot(bots[bot_id]),
    })

    return {
        "bot_id": bot_id,
        "status": "started",
        "mode": request.mode,
        "tf": request.tf,
        "symbol": request.symbol,
        "pid": proc.pid,
    }


def _kill_bot_proc(bot_id: str) -> Optional[int]:
    """Kill the subprocess for one bot (taskkill /F /T on Windows). Returns the killed pid."""
    proc = _bot_procs.get(bot_id)
    if proc is None or proc.poll() is not None:
        return None
    pid = proc.pid
    try:
        if sys.platform == 'win32':
            subprocess.run(
                ['taskkill', '/F', '/T', '/PID', str(pid)],
                capture_output=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            proc.terminate()
            try: proc.wait(timeout=5)
            except Exception: proc.kill()
        logger.info(f"Bot {bot_id} subprocess killed: pid={pid}")
    except Exception as e:
        logger.error(f"Failed to kill bot {bot_id} pid={pid}: {e}")
    return pid


async def _stop_one(bot_id: str, reason: str) -> dict:
    if bot_id not in bots:
        raise HTTPException(status_code=404, detail=f"Bot {bot_id} not found")
    killed_pid = _kill_bot_proc(bot_id)
    bots[bot_id]["status"] = "stopped"
    bots[bot_id]["bot_pid"] = None
    _bot_procs.pop(bot_id, None)
    _add_event(bot_id, "stopped", reason)
    _save_sessions()
    await manager.broadcast({"event": "bot_stopped", "bot_id": bot_id, "reason": reason})
    return {"bot_id": bot_id, "status": "stopped", "reason": reason, "killed_pid": killed_pid}


@app.post("/api/stop/{bot_id}")
async def stop_bot_by_id(bot_id: str, request: Optional[StopRequest] = None):
    """Stop one specific bot by id."""
    _sweep_dead()
    reason = request.reason if request else "User requested stop"
    return await _stop_one(bot_id, reason)


@app.post("/api/stop")
async def stop_all_bots(request: Optional[StopRequest] = None):
    """Stop every running bot. Used by global Stop All button + legacy callers."""
    _sweep_dead()
    reason = request.reason if request else "User requested stop"
    stopped = []
    for bot_id in list(bots.keys()):
        if bots[bot_id]["status"] == "running":
            stopped.append((await _stop_one(bot_id, reason))["bot_id"])
    return {"status": "stopped", "stopped": stopped, "count": len(stopped)}


@app.post("/api/emergency-stop")
async def emergency_stop():
    """Stop every bot immediately and clear open positions across all of them."""
    _sweep_dead()
    orders_count = 0
    stopped_ids = []
    for bot_id in list(bots.keys()):
        if bots[bot_id]["status"] == "running":
            orders_count += len(bots[bot_id].get("open_orders", []))
            _kill_bot_proc(bot_id)
            bots[bot_id]["status"] = "stopped"
            bots[bot_id]["bot_pid"] = None
            bots[bot_id]["open_orders"] = []
            _bot_procs.pop(bot_id, None)
            _add_event(bot_id, "emergency_stopped", "🚨 EMERGENCY STOP")
            stopped_ids.append(bot_id)
    _save_sessions()
    logger.warning(f"Emergency stop: {len(stopped_ids)} bots, {orders_count} orders cleared")
    await manager.broadcast({"event": "emergency_stop", "stopped": stopped_ids, "orders_closed": orders_count})
    return {"status": "emergency_stopped", "stopped": stopped_ids, "orders_closed": orders_count}


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


# ─── Trade History (analytics) ───────────────────────────────────────
# Reads from LocalDB (traider_backtest.db / traider_sim.db). Computes:
#   - List of normalized trade objects (filtered by date / mode / pattern / bot_id)
#   - Aggregate stats: winrate, P&L, drawdown, equity curve, consecutive streaks
# Used by TradeHistory.jsx — a single page showing every trade the system has
# ever taken, regardless of which bot opened it.

def _localdb_paths() -> List[str]:
    """Both DBs the bot might write to. Earlier/older runs land in different
    files, so the analytics page queries both and merges."""
    here = Path(__file__).resolve().parent
    candidates = [
        here / "traider_sim.db",
        here / "traider_backtest.db",
        here / os.getenv("LOCAL_DB_PATH", "traider_backtest.db"),
    ]
    seen, out = set(), []
    for p in candidates:
        s = str(p)
        if s in seen:
            continue
        seen.add(s)
        if p.exists():
            out.append(s)
    return out


def _parse_bot_id(bot_id: Optional[str]) -> tuple:
    """bot_id = '{tf}-{symbol}-{mode}'. Returns (tf, symbol, mode), each may be None."""
    if not bot_id:
        return (None, None, None)
    parts = bot_id.split("-")
    if len(parts) >= 3:
        return (parts[0], parts[1], parts[-1])
    return (None, None, None)


def _normalize_trade(row: dict, source_db: str) -> dict:
    """Map a LocalDB `trades` row to the TradeHistory schema the UI expects.
    Keeps the LocalDB row intact under `_raw` for debugging if anyone needs it."""
    tf, symbol, mode = _parse_bot_id(row.get("bot_id"))
    entry = row.get("entry_price")
    close = row.get("close_price")
    sl    = row.get("sl_price")
    tp    = row.get("tp_price")
    action = (row.get("action") or "").upper()

    pnl_pip = None
    if entry is not None and close is not None:
        # 1 pip = 0.01 USD on XAUUSD
        pnl_pip = round((close - entry) * 100 * (1 if action == "BUY" else -1), 1)

    rr_actual = None
    if entry is not None and close is not None and sl is not None:
        risk = abs(entry - sl)
        if risk > 0:
            reward = (close - entry) if action == "BUY" else (entry - close)
            rr_actual = round(reward / risk, 2)

    return {
        "trade_id":         row.get("trade_id"),
        "plan_id":          row.get("plan_id"),
        "bot_id":           row.get("bot_id"),
        "open_time":        row.get("timestamp_open"),
        "close_time":       row.get("timestamp_close"),
        "symbol":           symbol or "XAUUSDc",
        "timeframe":        row.get("timeframe") or tf,
        "direction":        action,
        "lot":              row.get("lot_size"),
        "entry_price":      entry,
        "sl_price":         sl,
        "tp_price":         tp,
        "close_price":      close,
        "result":           row.get("result"),
        "close_reason":     row.get("close_reason"),
        "pnl_usd":          row.get("pnl_usd"),
        "pnl_pip":          pnl_pip,
        "rr_actual":        rr_actual,
        "rr_planned":       row.get("rr_ratio"),
        "pattern":          row.get("chart_type"),
        "session":          row.get("session"),
        "claude_confidence": row.get("confidence"),
        "claude_reason":    row.get("ai_reason"),
        "mae_pip":          row.get("mae_pip"),
        "mfe_pip":          row.get("mfe_pip"),
        "r55_pip_at_open":  row.get("r55_pip_at_open"),
        "mode":             mode or "paper",
        "source_db":        Path(source_db).name,
    }


def _load_trades_from_db(
    from_date: Optional[str],
    to_date: Optional[str],
    mode: Optional[str],
    pattern: Optional[str],
    bot_id: Optional[str],
) -> List[dict]:
    """Pull rows from every LocalDB file we know about, normalize, merge,
    and apply filters. Date filter applies to timestamp_open."""
    import sqlite3
    all_rows: List[dict] = []
    for db_path in _localdb_paths():
        try:
            con = sqlite3.connect(db_path)
            con.row_factory = sqlite3.Row
            q = "SELECT * FROM trades"
            conds, params = [], []
            if bot_id:
                conds.append("bot_id = ?")
                params.append(bot_id)
            if from_date:
                conds.append("timestamp_open >= ?")
                params.append(from_date)
            if to_date:
                # to_date is inclusive — extend to end-of-day
                conds.append("timestamp_open < ?")
                params.append(to_date + "T23:59:59" if "T" not in to_date else to_date)
            if conds:
                q += " WHERE " + " AND ".join(conds)
            q += " ORDER BY timestamp_open"
            try:
                cur = con.execute(q, params)
            except sqlite3.OperationalError:
                # Older DB without some columns — skip silently.
                con.close()
                continue
            for r in cur.fetchall():
                all_rows.append(_normalize_trade(dict(r), db_path))
            con.close()
        except Exception as e:
            logger.warning(f"_load_trades_from_db({db_path}): {e}")
            continue

    # Mode / pattern filters — applied post-normalize so they handle the bot_id parse.
    if mode and mode != "all":
        all_rows = [t for t in all_rows if (t.get("mode") or "").lower() == mode.lower()]
    if pattern and pattern != "all":
        all_rows = [t for t in all_rows if (t.get("pattern") or "").upper() == pattern.upper()]

    # Sort by open_time, newest last (UI flips to desc).
    all_rows.sort(key=lambda t: t.get("open_time") or "")
    return all_rows


def _compute_trade_stats(trades: List[dict], initial_balance: float = 1000.0) -> dict:
    """Aggregate stats over normalized trades.
    Equity curve uses cumulative pnl_usd starting from initial_balance.
    Drawdown is computed against the running peak of that curve."""
    closed = [t for t in trades if t.get("result") in ("WIN", "LOSS")]
    wins   = [t for t in closed if t["result"] == "WIN"]
    losses = [t for t in closed if t["result"] == "LOSS"]

    total_pnl_usd = round(sum(t.get("pnl_usd") or 0 for t in closed), 2)
    total_pnl_pip = round(sum(t.get("pnl_pip") or 0 for t in closed), 1)
    wr_pct        = round(len(wins) / len(closed) * 100, 1) if closed else 0.0

    best  = max(closed, key=lambda t: t.get("pnl_usd") or 0, default=None)
    worst = min(closed, key=lambda t: t.get("pnl_usd") or 0, default=None)

    rr_actuals  = [t["rr_actual"] for t in wins if t.get("rr_actual") is not None]
    rr_planneds = [t["rr_planned"] for t in closed if t.get("rr_planned")]
    avg_rr_actual  = round(sum(rr_actuals) / len(rr_actuals), 2) if rr_actuals else 0.0
    avg_rr_planned = round(sum(rr_planneds) / len(rr_planneds), 2) if rr_planneds else 0.0

    # Equity curve + drawdown
    balance = initial_balance
    peak = initial_balance
    max_dd_pct = 0.0
    max_dd_usd = 0.0
    equity_curve: List[dict] = [{
        "t": trades[0]["open_time"] if trades else None,
        "balance": round(balance, 2),
        "drawdown_pct": 0.0,
        "drawdown_usd": 0.0,
        "trade_id": None,
    }]
    for t in closed:
        balance += (t.get("pnl_usd") or 0)
        if balance > peak:
            peak = balance
        dd_usd = peak - balance
        dd_pct = (dd_usd / peak * 100) if peak > 0 else 0.0
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct
        if dd_usd > max_dd_usd:
            max_dd_usd = dd_usd
        equity_curve.append({
            "t": t.get("close_time") or t.get("open_time"),
            "balance": round(balance, 2),
            "drawdown_pct": round(-dd_pct, 2),  # negative for chart
            "drawdown_usd": round(-dd_usd, 2),
            "trade_id": t.get("trade_id"),
        })

    # Consecutive streaks
    max_win_streak  = 0
    max_loss_streak = 0
    cur_win  = 0
    cur_loss = 0
    for t in closed:
        if t["result"] == "WIN":
            cur_win += 1
            cur_loss = 0
            max_win_streak = max(max_win_streak, cur_win)
        else:
            cur_loss += 1
            cur_win = 0
            max_loss_streak = max(max_loss_streak, cur_loss)

    # Pattern breakdown
    by_pattern: Dict[str, dict] = {}
    for t in closed:
        pat = t.get("pattern") or "UNKNOWN"
        d = by_pattern.setdefault(pat, {"pattern": pat, "total": 0, "wins": 0, "losses": 0, "net_usd": 0.0})
        d["total"] += 1
        if t["result"] == "WIN":  d["wins"]   += 1
        if t["result"] == "LOSS": d["losses"] += 1
        d["net_usd"] += (t.get("pnl_usd") or 0)
    pattern_breakdown = []
    for d in by_pattern.values():
        d["wr_pct"] = round(d["wins"] / d["total"] * 100, 1) if d["total"] else 0.0
        d["net_usd"] = round(d["net_usd"], 2)
        pattern_breakdown.append(d)
    pattern_breakdown.sort(key=lambda d: d["total"], reverse=True)

    return {
        "total_trades":     len(trades),
        "closed_trades":    len(closed),
        "pending":          sum(1 for t in trades if t.get("result") == "PENDING"),
        "wins":             len(wins),
        "losses":           len(losses),
        "wr_pct":           wr_pct,
        "total_pnl_usd":    total_pnl_usd,
        "total_pnl_pip":    total_pnl_pip,
        "best_trade":       {"pnl_usd": best.get("pnl_usd"),  "trade_id": best.get("trade_id"),  "pattern": best.get("pattern")}  if best  else None,
        "worst_trade":      {"pnl_usd": worst.get("pnl_usd"), "trade_id": worst.get("trade_id"), "pattern": worst.get("pattern")} if worst else None,
        "avg_rr_actual":    avg_rr_actual,
        "avg_rr_planned":   avg_rr_planned,
        "max_drawdown_pct": round(max_dd_pct, 2),
        "max_drawdown_usd": round(max_dd_usd, 2),
        "max_win_streak":   max_win_streak,
        "max_loss_streak":  max_loss_streak,
        "current_balance":  round(balance, 2),
        "starting_balance": initial_balance,
        "peak_balance":     round(peak, 2),
        "equity_curve":     equity_curve,
        "pattern_breakdown": pattern_breakdown,
    }


@app.get("/api/trades")
async def list_trades(
    from_date: Optional[str] = Query(None, alias="from"),
    to_date:   Optional[str] = Query(None, alias="to"),
    mode:      Optional[str] = "all",
    pattern:   Optional[str] = "all",
    bot_id:    Optional[str] = None,
    limit:     int = 1000,
):
    """List trades for TradeHistory.jsx. Accepts ?from=YYYY-MM-DD&to=YYYY-MM-DD."""
    trades = _load_trades_from_db(from_date, to_date, mode, pattern, bot_id)
    # Truncate to `limit` newest (page itself paginates client-side).
    if len(trades) > limit:
        trades = trades[-limit:]
    return {"trades": trades, "count": len(trades)}


@app.get("/api/trades/stats")
async def trade_stats(
    from_date: Optional[str] = Query(None, alias="from"),
    to_date:   Optional[str] = Query(None, alias="to"),
    mode:      Optional[str] = "all",
    pattern:   Optional[str] = "all",
    bot_id:    Optional[str] = None,
    initial_balance: float = 1000.0,
):
    """Aggregate analytics for TradeHistory.jsx. Same filters as /api/trades."""
    trades = _load_trades_from_db(from_date, to_date, mode, pattern, bot_id)
    stats = _compute_trade_stats(trades, initial_balance=initial_balance)
    return stats


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


# ─── Shared candle cache ─────────────────────────────────────────────
# Two scenarios this prevents:
#   1. Multiple bots fetching the same (tf, symbol) within seconds — they hit
#      the cache instead of pounding MT5 / yfinance independently.
#   2. UI polling /api/candles every few seconds — same cache path.
# TTL is keyed to TF size so M1 expires fast (10s) and H4 expires slowly (300s).
_candles_cache: Dict[tuple, dict] = {}  # (source, tf, symbol, limit) -> {"ts": float, "data": list}

_CANDLE_TTL_SEC = {
    "M1": 10, "M5": 30, "M15": 60, "M30": 90, "H1": 180, "H4": 300,
}


def _fetch_candles_mt5(sym: str, tf: str, limit: int) -> list:
    try:
        import MetaTrader5 as mt5
    except ImportError:
        logger.error("MetaTrader5 module not installed")
        return []
    tf_map = {
        "M1":  mt5.TIMEFRAME_M1,  "M5":  mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30,
        "H1":  mt5.TIMEFRAME_H1,  "H4":  mt5.TIMEFRAME_H4,
    }
    mt5_tf = tf_map.get(tf.upper())
    if mt5_tf is None:
        return []
    try:
        if not mt5.initialize():
            logger.warning(f"mt5.initialize() failed: {mt5.last_error()}")
            return []
        si = mt5.symbol_info(sym)
        if si is None:
            logger.warning(f"Symbol {sym} not found")
            return []
        if not si.visible:
            mt5.symbol_select(sym, True)
        rates = mt5.copy_rates_from_pos(sym, mt5_tf, 0, limit)
        if rates is None or len(rates) == 0:
            return []
        return [
            {
                "time":  int(r["time"]),
                "open":  float(r["open"]),
                "high":  float(r["high"]),
                "low":   float(r["low"]),
                "close": float(r["close"]),
                "volume": int(r["tick_volume"]),
            }
            for r in rates
        ]
    except Exception as e:
        logger.error(f"MT5 candle fetch failed: {e}")
        return []


@app.get("/api/candles")
async def get_candles(tf: str = "M5", limit: int = 100, symbol: str = None,
                      source: str = "mt5", force: bool = False):
    """Latest OHLC candles. Cached by (source, tf, symbol, limit) with a
    TF-sized TTL so concurrent bots / UI polls share one fetch."""
    import time as _time
    sym = symbol or bot_state.get("symbol", "XAUUSDc")
    key = (source, tf.upper(), sym, limit)
    ttl = _CANDLE_TTL_SEC.get(tf.upper(), 60)
    now = _time.time()

    if not force:
        cached = _candles_cache.get(key)
        if cached and (now - cached["ts"]) < ttl:
            return cached["data"]

    if source == "mt5":
        data = _fetch_candles_mt5(sym, tf, limit)
    else:
        # Future: yfinance/tv branches — keep the cache contract identical.
        logger.warning(f"/api/candles: source '{source}' not implemented, falling back to MT5")
        data = _fetch_candles_mt5(sym, tf, limit)

    _candles_cache[key] = {"ts": now, "data": data}
    return data


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "bot_status": bot_state["status"]
    }


@app.get("/api/mt5-status")
async def mt5_status():
    """
    Live MT5 connectivity check — queries terminal/account/symbol on demand.
    UI polls this to verify MT5 connection + see real-time tick.

    Returns:
        {
            connected: bool,
            terminal: {connected, trade_allowed, build},
            account: {login, server, balance, currency, leverage} | null,
            symbol: {name, bid, ask, spread_pip, time} | null,
            error: str | null
        }
    """
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return {"connected": False, "error": "MetaTrader5 module not installed"}

    sym_name = bot_state.get("symbol", "XAUUSDc")
    out = {"connected": False, "terminal": None, "account": None, "symbol": None, "error": None}

    try:
        # Initialize if not already (idempotent — returns True if already connected)
        if not mt5.initialize():
            out["error"] = f"mt5.initialize() failed: {mt5.last_error()}"
            return out

        ti = mt5.terminal_info()
        if ti is None:
            out["error"] = "terminal_info() returned None"
            return out
        out["terminal"] = {
            "connected": ti.connected,
            "trade_allowed": ti.trade_allowed,
            "build": ti.build,
        }
        if not ti.connected:
            out["error"] = "MT5 terminal not connected to broker"
            return out

        ai = mt5.account_info()
        if ai is None:
            out["error"] = "account_info() returned None — not logged in"
            return out
        out["account"] = {
            "login": ai.login,
            "server": ai.server,
            "balance": float(ai.balance),
            "equity": float(ai.equity),
            "profit": float(ai.profit),         # floating P/L on open positions
            "margin": float(ai.margin),         # margin used by open positions
            "margin_free": float(ai.margin_free),
            "margin_level": float(ai.margin_level) if ai.margin_level else None,  # %
            "currency": ai.currency,
            "leverage": ai.leverage,
            "trade_mode": ai.trade_mode,  # 0=demo, 2=real
        }
        # Open positions count — useful "is anything live right now"
        try:
            positions = mt5.positions_get(symbol=sym_name)
            out["account"]["positions_count"] = len(positions) if positions else 0
        except Exception:
            out["account"]["positions_count"] = None

        si = mt5.symbol_info(sym_name)
        if si is None:
            out["error"] = f"symbol {sym_name} not found"
            return out
        if not si.visible:
            mt5.symbol_select(sym_name, True)

        tick = mt5.symbol_info_tick(sym_name)
        if tick is None:
            out["error"] = f"no tick for {sym_name}"
            return out
        out["symbol"] = {
            "name": sym_name,
            "bid": float(tick.bid),
            "ask": float(tick.ask),
            "spread_pip": round((tick.ask - tick.bid) * 100, 1),
            "time": datetime.fromtimestamp(tick.time).isoformat(),
        }
        out["connected"] = True
        return out

    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
        return out


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
# BACKTEST ENDPOINTS
# ============================================================================

@app.post("/api/backtest/run")
async def run_backtest(request: Request):
    """
    Run backtest in background

    Body:
        {
            "start": "2026-04-01",
            "end": "2026-04-21"
        }
    """
    global _backtest_state

    if _backtest_state["is_running"]:
        return {"status": "already_running",
                "message": "Backtest กำลังรันอยู่"}

    body = await request.json()
    start     = body.get("start", "2026-04-01")
    end       = body.get("end",   "2026-04-21")
    timeframe = body.get("timeframe", "M5").upper()

    # Validate timeframe
    valid_tfs = ["M1", "M5", "M15", "M30", "H1", "H4"]
    if timeframe not in valid_tfs:
        return {"status": "error",
                "message": f"Timeframe ต้องเป็นหนึ่งใน {valid_tfs}"}

    # Validate date format
    try:
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt   = datetime.strptime(end,   "%Y-%m-%d")
    except:
        return {"status": "error",
                "message": "รูปแบบวันที่ไม่ถูกต้อง (YYYY-MM-DD)"}

    # Validate range
    if end_dt <= start_dt:
        return {"status": "error",
                "message": "End date ต้องมากกว่า Start date"}

    days = (end_dt - start_dt).days
    MAX_DAYS = 60  # yfinance 5m data limit
    if days > MAX_DAYS:
        return {"status": "error",
                "message": f"ช่วงเวลาสูงสุด {MAX_DAYS} วัน (เลือก {days} วัน)"}

    # Validate ไม่เกินวันนี้
    if end_dt > datetime.now():
        return {"status": "error",
                "message": "End date ต้องไม่เกินวันปัจจุบัน"}

    # Clear LocalDB ก่อนรัน
    try:
        from utils.local_db import LocalDB
        db = LocalDB()
        db.clear_trades()
        db.close()
        logger.info(f"✅ LocalDB cleared, starting backtest {start} → {end}")
    except Exception as e:
        logger.error(f"LocalDB clear failed: {e}")

    # อัปเดต state
    _backtest_state["start"]     = start
    _backtest_state["end"]       = end
    _backtest_state["timeframe"] = timeframe

    # รันใน background thread
    t = threading.Thread(
        target=_run_backtest_thread,
        args=(start, end, timeframe),
        daemon=True
    )
    t.start()

    return {"status": "started", "start": start, "end": end, "timeframe": timeframe}


@app.get("/api/backtest/results")
async def get_backtest_results():
    """
    Get backtest results from LocalDB

    Returns:
        {
            "status": "done" | "running" | "error",
            "summary": {...},
            "by_pattern": [...],
            "trades": [...],
            "equity_curve": [...]
        }
    """
    if _backtest_state["is_running"]:
        return {"status": "running", "message": "ยังรันอยู่"}

    try:
        from utils.local_db import LocalDB
        db = LocalDB()
        return {
            "status":       "done",
            "summary":      db.get_summary(),
            "by_pattern":   db.get_summary_by_pattern(),
            "trades":       db.get_all_trades()[-100:],
            "equity_curve": db.get_equity_curve(initial_balance=1000.0),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        if 'db' in locals():
            db.close()


@app.get("/api/backtest/status")
async def get_backtest_status():
    """
    Get backtest progress status

    Returns:
        {
            "is_running": bool,
            "trades_so_far": int,
            "wins": int,
            "losses": int,
            "pending": int,
            "start": str,
            "end": str,
            "error": str | None
        }
    """
    from utils.local_db import LocalDB
    db = LocalDB()
    s  = db.get_summary()

    wins   = s.get("wins", 0) or 0
    losses = s.get("losses", 0) or 0
    pending= s.get("pending", 0) or 0
    total  = wins + losses + pending

    return {
        "is_running":    _backtest_state["is_running"],
        "trades_so_far": total,
        "wins":          wins,
        "losses":        losses,
        "pending":       pending,
        "start":         _backtest_state.get("start"),
        "end":           _backtest_state.get("end"),
        "error":         _backtest_state.get("error"),
    }


# ============================================================================
# STRATEGY MANAGER ENDPOINTS (V65)
# ============================================================================

@app.get("/api/strategies")
async def get_strategies():
    """Strategy config + per-pattern allowed_tfs (resolved against ALL_TFS default)."""
    from utils.strategy_loader import load_config, get_active_patterns, get_allowed_tfs, ALL_TFS

    try:
        config = load_config()
        patterns = config.get("patterns", {})
        active = get_active_patterns()

        # Materialize allowed_tfs so the frontend always gets an explicit list
        # (even when the JSON omits the key — then it's "all TFs allowed").
        for name, meta in patterns.items():
            meta["allowed_tfs"] = get_allowed_tfs(name)

        return {
            "version": config.get("version", "?"),
            "patterns": patterns,
            "active_count": len(active),
            "active_patterns": active,
            "all_tfs": list(ALL_TFS),
            "last_updated": config.get("last_updated", ""),
        }
    except Exception as e:
        logger.error(f"Failed to load strategies: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/strategies")
async def update_strategies(request: Request):
    """Update active patterns and/or per-pattern allowed_tfs.

    Body (both fields optional, applied independently):
        {
          "active": ["MOUNTAIN", "MAI_RUAY"],
          "allowed_tfs": {"MOUNTAIN": ["M1", "M5"]}
        }
    """
    from utils.strategy_loader import (
        save_active, save_allowed_tfs, get_active_patterns, get_allowed_tfs,
    )

    try:
        body = await request.json()
        active_list = body.get("active")
        tfs_map = body.get("allowed_tfs")

        if active_list is not None:
            if not isinstance(active_list, list):
                return JSONResponse(status_code=400,
                                    content={"error": "active must be a list of pattern names"})
            save_active(active_list)

        if tfs_map is not None:
            if not isinstance(tfs_map, dict):
                return JSONResponse(status_code=400,
                                    content={"error": "allowed_tfs must be a {pattern: [tf, ...]} object"})
            save_allowed_tfs(tfs_map)

        if active_list is None and tfs_map is None:
            return JSONResponse(status_code=400,
                                content={"error": "Provide 'active' and/or 'allowed_tfs'"})

        updated_active = get_active_patterns()
        updated_tfs = {p: get_allowed_tfs(p) for p in (tfs_map or {}).keys()}

        logger.info(f"Strategies updated. active={updated_active} allowed_tfs={updated_tfs}")
        return {
            "success": True,
            "active_patterns": updated_active,
            "allowed_tfs": updated_tfs,
        }
    except Exception as e:
        logger.error(f"Failed to update strategies: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


# ============================================================================
# STARTUP / SHUTDOWN EVENTS
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
    logger.info("🚀 API Server starting...")
    logger.info("📊 Dashboard available at http://127.0.0.1:8080")
    # Tier 3: start the live tick poller (broadcasts MT5 bid/ask via WebSocket)
    asyncio.create_task(_tick_poll_loop())


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("🛑 API Server shutting down...")
    global _tick_poll_running
    _tick_poll_running = False


# ─── Tier 3: Live tick stream ──────────────────────────────────────
# Broadcasts MT5 bid/ask for each unique symbol any running bot uses.
# One MT5 connection (already used by /api/mt5-status), polled every
# TICK_POLL_SECONDS. Cached so /api/ticks can serve REST requests too.
_latest_ticks: Dict[str, dict] = {}
_tick_poll_running = True
TICK_POLL_SECONDS = 2.0


def _active_symbols() -> List[str]:
    """Distinct symbols across running bots. Empty list if none — poller idles."""
    return list({b["symbol"] for b in bots.values() if b["status"] == "running"})


async def _tick_poll_loop() -> None:
    """Background poller — fetches MT5 tick per active symbol every
    TICK_POLL_SECONDS, caches in _latest_ticks, broadcasts via WebSocket
    as {event: 'tick', ...}. Survives transient MT5 hiccups silently."""
    try:
        import MetaTrader5 as mt5
    except ImportError:
        logger.warning("Tick poller: MetaTrader5 module not installed — disabled")
        return

    logger.info(f"📡 Tick poller started (every {TICK_POLL_SECONDS}s)")
    while _tick_poll_running:
        try:
            symbols = _active_symbols()
            if not symbols:
                # Nothing to poll — sleep longer to avoid spinning
                await asyncio.sleep(5.0)
                continue

            if not mt5.initialize():
                await asyncio.sleep(TICK_POLL_SECONDS)
                continue

            for sym in symbols:
                try:
                    si = mt5.symbol_info(sym)
                    if si is None:
                        continue
                    if not si.visible:
                        mt5.symbol_select(sym, True)
                    tick = mt5.symbol_info_tick(sym)
                    if tick is None:
                        continue
                    payload = {
                        "symbol": sym,
                        "bid": float(tick.bid),
                        "ask": float(tick.ask),
                        "spread_pip": round((tick.ask - tick.bid) * 100, 1),
                        "time": datetime.fromtimestamp(tick.time).isoformat(),
                        "ts": datetime.now().isoformat(),
                    }
                    _latest_ticks[sym] = payload
                    await manager.broadcast({"event": "tick", **payload})
                except Exception as e:
                    logger.debug(f"Tick poll {sym}: {e}")

        except Exception as e:
            logger.error(f"Tick poll loop error: {e}")

        await asyncio.sleep(TICK_POLL_SECONDS)
    logger.info("📡 Tick poller stopped")


@app.get("/api/ticks")
async def get_latest_ticks():
    """REST snapshot of every symbol's most recent tick (poller updates every
    TICK_POLL_SECONDS). UI can use this on first load before WS catches up."""
    return {"ticks": _latest_ticks, "poll_seconds": TICK_POLL_SECONDS}


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


def set_connector(connector_instance):
    """
    Set Connector instance (MT5Connector or TVConnector) for /api/candles

    Usage:
        from api_server import set_connector
        set_connector(self.connector)
    """
    global connector
    connector = connector_instance


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
    print("📊 Dashboard: http://127.0.0.1:8000")
    print("📡 API Docs:  http://127.0.0.1:8080/docs")
    print("🔌 WebSocket: ws://127.0.0.1:8080/ws")
    print("="*70)

    uvicorn.run(
        app,
        host="127.0.0.1",  # localhost only — DO NOT change to 0.0.0.0
        port=8080,
        log_level="info"
    )
