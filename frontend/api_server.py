"""
Tra(i)der Phase I v2.1 - FastAPI Backend Server
Provides REST API and WebSocket for real-time updates
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import json
import asyncio
from typing import List
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(title="Tra(i)der API", version="2.1.0")

# CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients"""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()

# Global state (will be updated by main.py)
bot_state = {
    "bot_status": "stopped",
    "mode": "backtest",
    "current_price": 0,
    "balance": 500,
    "total_pnl": 0,
    "total_pnl_pct": 0,
    "open_positions": 0,
    "total_trades": 0,
    "win_rate": 0,
    "avg_rr": 0,
    "sharpe": 0,
    "max_dd": 0,
    "data_source_actual": "TradingView",
    "recent_trades": [],
    "agent_activities": [],
    "portfolio": {
        "balance": 500,
        "equity": 500,
        "total_pnl": 0,
        "total_pnl_pct": 0,
        "open_positions": 0,
        "consecutive_loss": 0,
        "active_plan_id": None,
    },
    "world_state": {
        "trend": "unclear",
        "chart_quality": 0,
        "twin_candle": False,
        "breakout_box": False,
        "mountain_detected": False,
        "technique_candidate": None,
    },
    "last_decision": None,
}

# API Routes
@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "2.1.0"}

@app.get("/api/state")
async def get_state():
    """Get current bot state"""
    return bot_state

@app.post("/api/update-state")
async def update_state(data: dict):
    """Update bot state and broadcast to clients"""
    bot_state.update(data)
    await manager.broadcast({"type": "state_update", "data": bot_state})
    return {"status": "ok"}

# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    
    # Send initial state
    try:
        await websocket.send_json({
            "type": "initial_state",
            "data": bot_state
        })
        
        # Keep connection alive
        while True:
            data = await websocket.receive_text()
            # Echo back for now (can add commands later)
            await websocket.send_text(f"Received: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Serve static files in production
static_build_path = Path(__file__).parent / "static_build"
if static_build_path.exists():
    app.mount("/assets", StaticFiles(directory=static_build_path / "assets"), name="assets")
    
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve React SPA"""
        # If requesting a file that exists, serve it
        file_path = static_build_path / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        # Otherwise serve index.html (for client-side routing)
        return FileResponse(static_build_path / "index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
