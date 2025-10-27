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
from ..core.state import Portfolio   # new import (manager already has one)
from datetime import datetime, timezone

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
    snap = await manager.portfolio.snapshot()
    unreal = await manager.portfolio.compute_unrealized()
    total = float(snap["realized"]) + float(unreal["unrealized"])

    # wrap and add timestamp; keep old keys too
    return {
        "ok": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total": total,
        "realized": float(snap["realized"]),
        "unrealized": float(unreal["unrealized"]),
        "bySymbol": unreal["bySymbol"],        # [{symbol, unrealized}]
        # optional for some UIs
        "summary": {
            "total": total,
            "realized": float(snap["realized"]),
            "unrealized": float(unreal["unrealized"]),
            "symbols": [x["symbol"] for x in unreal["bySymbol"]],
        },
    }

@app.get("/api/positions")
async def api_positions():
    snap = await manager.portfolio.snapshot()
    items = []
    for p in snap["positions"]:
        # normalize field names commonly used by dashboards
        items.append({
            "symbol": p["symbol"],
            "qty": float(p.get("qty", 0.0)),
            "avg_entry": float(p.get("avg_entry", 0.0)),
        })
    return {
        "ok": True,
        "count": len(items),
        "items": items,     # <--- UI-friendly wrapper
    }

@app.get("/api/trades")
async def api_trades(limit: int = 100):
    snap = await manager.portfolio.snapshot()
    trades = list(reversed(snap["trades"][-limit:]))

    # normalize field names and add an id the UI can key by
    items = []
    for i, t in enumerate(trades, 1):
        items.append({
            "id": i,
            "ts": t["ts"],
            "symbol": t["symbol"],
            "side": t["side"],
            "qty": float(t["qty"]),
            "price": float(t["price"]),
            "fees": float(t.get("fees", 0.0)),
            "maker": bool(t.get("maker", True)),
            "reason": t.get("reason") or "",
            # extra convenience fields many UIs expect:
            "notional": float(t["qty"]) * float(t["price"]),
        })

    return {
        "ok": True,
        "count": len(items),
        "items": items,    # <--- UI-friendly wrapper
    }

# ---- Diagnostics (new) ----
@app.get("/api/diag")
async def api_diag():
    return {
        "mode": settings.MODE,
        "live": settings.LIVE,
        "allowed_symbols": settings.ALLOWED_SYMBOLS,
        "agents": manager.list()
    }

# --- quick market-data health check ---
from fastapi import Query
from ..services.pricefeed import PriceFeed
from ..agents.manager import AgentManager  # already imported, reuse manager.pricefeed

@app.get("/api/diag/pricefeed")
async def api_diag_pricefeed(symbols: str = Query(None, description="CSV of symbols, defaults to ALLOWED_SYMBOLS")):
    syms = [s.strip() for s in (symbols.split(",") if symbols else manager.list()[0]["symbols"]) if s.strip()] if manager.list() else []
    pf = manager.pricefeed
    out = {}
    for s in syms:
        ob = await pf.get_orderbook(s)
        bids = ob.get("bids", [])
        asks = ob.get("asks", [])
        bb = bids[0][0] if bids else None
        ba = asks[0][0] if asks else None
        kl = await pf.get_recent_klines(s, limit=300)
        out[s] = {
            "best_bid": bb, "best_ask": ba,
            "bids": len(bids), "asks": len(asks),
            "candles": len(kl)
        }
    return out
