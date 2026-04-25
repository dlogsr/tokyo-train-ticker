"""
Tokyo Train Ticker — FastAPI backend
Serves REST API + WebSocket for real-time updates.
Static frontend files are also served from here.
"""
import asyncio
import json
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from odpt_client import ODPTClient
from line_data import LINES, STATIONS

ODPT_KEY = os.getenv("ODPT_API_KEY")  # optional — demo mode if not set
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

app = FastAPI(title="Tokyo Train Ticker")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

client = ODPTClient(api_key=ODPT_KEY)

# ── REST endpoints ────────────────────────────────────────────────────────────

@app.get("/api/status")
def status():
    return {
        "demo_mode": ODPT_KEY is None,
        "api_key_configured": ODPT_KEY is not None,
        "lines": len(LINES),
        "stations": len(STATIONS),
    }

@app.get("/api/lines")
def list_lines():
    return [
        {
            "code": code,
            "name": data["name"],
            "short": data["short"],
            "color": data["color"],
            "text_color": data["text"],
            "shape": data["shape"],
            "operator": data["operator"],
        }
        for code, data in LINES.items()
    ]

@app.get("/api/stations")
def list_stations():
    return [
        {
            "id": sid,
            "name_en": s["name_en"],
            "name_ja": s["name_ja"],
            "lines": s["lines"],
        }
        for sid, s in sorted(STATIONS.items(), key=lambda x: x[1]["name_en"])
    ]

@app.get("/api/trains/station/{station_id}")
async def trains_at_station(station_id: str):
    return await client.get_trains_at_station(station_id)

@app.get("/api/trains/line/{line_code}")
async def trains_on_line(line_code: str):
    return await client.get_trains_on_line(line_code)

@app.get("/api/stations/{station_id}")
def station_detail(station_id: str):
    s = STATIONS.get(station_id)
    if not s:
        return {"error": "station not found"}
    return {
        "id": station_id,
        "name_en": s["name_en"],
        "name_ja": s["name_ja"],
        "lines": [
            {
                "code": lc,
                "name": LINES[lc]["name"],
                "short": LINES[lc]["short"],
                "color": LINES[lc]["color"],
                "text_color": LINES[lc]["text"],
                "shape": LINES[lc]["shape"],
            }
            for lc in s["lines"] if lc in LINES
        ],
    }

# ── WebSocket for real-time push ──────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self._active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._active.append(ws)

    def disconnect(self, ws: WebSocket):
        self._active.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self._active:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._active.remove(ws)

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            msg = await websocket.receive_json()
            mode = msg.get("mode")
            if mode == "station":
                station_id = msg.get("station_id", "shibuya")
                trains = await client.get_trains_at_station(station_id)
                await websocket.send_json({"type": "station_update", "station_id": station_id, "trains": trains})
            elif mode == "line":
                line_code = msg.get("line_code", "JY")
                trains = await client.get_trains_on_line(line_code)
                await websocket.send_json({"type": "line_update", "line_code": line_code, "trains": trains})
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Background task: push updates to all connected clients every 15s
@app.on_event("startup")
async def start_push_loop():
    asyncio.create_task(_push_loop())

async def _push_loop():
    while True:
        await asyncio.sleep(15)
        # Push a heartbeat; clients re-request their own view
        await manager.broadcast({"type": "tick"})

# ── Serve frontend static files ────────────────────────────────────────────────
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    @app.get("/{path:path}")
    def serve_file(path: str):
        target = FRONTEND_DIR / path
        if target.exists() and target.is_file():
            return FileResponse(str(target))
        return FileResponse(str(FRONTEND_DIR / "index.html"))
