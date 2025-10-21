# app/api/main.py
from fastapi import FastAPI, HTTPException
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, PlainTextResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from typing import Any, Dict, List
from datetime import datetime
import logging

from ..core.logging import setup_logging
from ..core.config import settings
from ..core.metrics import kill_switch
from ..agents.manager import AgentManager

log = logging.getLogger("api")

app = FastAPI(title="Crypto Agents Pro", version="1.0.0")
setup_logging()

manager = AgentManager()
log.info("API boot: mode=%s live=%s symbols=%s", settings.MODE, settings.LIVE, settings.ALLOWED_SYMBOLS)

# ---- Static web ----
app.mount("/web", StaticFiles(directory=Path("web")), name="web")
app.mount("/ui", StaticFiles(directory=Path("web")), name="ui")  # keep legacy /ui path

@app.get("/")
async def root():
    return RedirectResponse(url="/web/index.html")

# ---- Metrics ----
@app.get("/metrics")
async def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)

# ---- Agent management (existing) ----
@app.get("/api/agents")
async def api_agents():
    return manager.list()

@app.post("/api/agents/start_all")
async def api_agents_start_all():
    if int(kill_switch._value.get()) == 1:
        raise HTTPException(409, "Kill switch enabled")
    await manager.start_all()
    return {"ok": True}

@app.post("/api/agents/stop_all")
async def api_agents_stop_all():
    await manager.stop_all()
    return {"ok": True}

@app.post("/api/agents/start/{name}")
async def api_agent_start(name: str):
    names = [a["name"] for a in manager.list()]
    if name not in names:
        raise HTTPException(404, "Agent not found")
    if int(kill_switch._value.get()) == 1:
        raise HTTPException(409, "Kill switch enabled")
    await manager.start(name)
    return {"ok": True}

@app.post("/api/agents/stop/{name}")
async def api_agent_stop(name: str):
    names = [a["name"] for a in manager.list()]
    if name not in names:
        raise HTTPException(404, "Agent not found")
    await manager.stop(name)
    return {"ok": True}

# ---- UI compatibility ----
@app.post("/api/agents/start")
async def api_agents_start():
    if int(kill_switch._value.get()) == 1:
        raise HTTPException(409, "Kill switch enabled")
    await manager.start_all()
    return {"ok": True, "started": [a["name"] for a in manager.list()]}

@app.post("/api/agents/stop")
async def api_agents_stop():
    await manager.stop_all()
    return {"ok": True, "stopped": [a["name"] for a in manager.list()]}

@app.get("/api/build")
async def api_build():
    return {"name": "Crypto Agents Pro", "version": "1.0.0", "mode": settings.MODE, "time": datetime.utcnow().isoformat() + "Z"}

@app.get("/api/status")
async def api_status():
    return {"running": True, "mode": settings.MODE, "agents": manager.list()}

@app.get("/api/pnl")
async def api_pnl():
    return {"total": 0.0, "realized": 0.0, "unrealized": 0.0, "bySymbol": []}

@app.get("/api/positions")
async def api_positions():
    return []

@app.get("/api/trades")
async def api_trades(limit: int = 100):
    return []

# ---- Diagnostics (new) ----
@app.get("/api/diag")
async def api_diag():
    return {
        "mode": settings.MODE,
        "live": settings.LIVE,
        "allowed_symbols": settings.ALLOWED_SYMBOLS,
        "agents": manager.list()
    }
