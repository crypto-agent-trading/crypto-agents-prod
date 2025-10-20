from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pathlib import Path
import subprocess

from ..core.logging import setup_logging
from ..core.config import settings
from ..core.metrics import kill_switch
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from ..agents.manager import AgentManager

from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse


setup_logging()
app = FastAPI(title="Crypto Agents Pro")


###

@app.middleware("http")
async def _no_cache_ui(request, call_next):
    resp = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/ui"):
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    return resp



# (You likely already have these two from earlier; keep them)
app.mount("/ui", StaticFiles(directory=str(Path(__file__).resolve().parents[2] / "web"), html=True), name="ui")

@app.get("/", include_in_schema=False)
def root_redirect():
    return RedirectResponse(url="/ui/")

# NEW: no-cache for UI
@app.middleware("http")
async def _no_cache_ui(request, call_next):
    resp = await call_next(request)
    p = request.url.path
    if p == "/" or p.startswith("/ui"):
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    return resp


##

manager = AgentManager(state_dir=(Path(__file__).resolve().parents[2] / "data"))
# seed if empty
manager.upsert({"name":"market-scanner","type":"market_scanner","symbols":settings.ALLOWED_SYMBOLS,"config":{"interval_sec":2,"mom_thresh":0.25,"qty":1}})
manager.upsert({"name":"depth-l1l3","type":"depth_l1l3","symbols":[settings.ALLOWED_SYMBOLS[0]],"config":{"interval_sec":3,"imbalance_thresh":0.6,"qty":1}})
manager.upsert({"name":"indicator","type":"indicator","symbols":settings.ALLOWED_SYMBOLS,"config":{"rsi_period":14,"rsi_buy":55,"rsi_sell":45,"interval_sec":3,"qty":1}})
manager.upsert({"name":"execution","type":"execution","symbols":settings.ALLOWED_SYMBOLS,"config":{"interval_sec":1}})
manager.build_all()
kill_switch.set(0)

@app.get("/api/agents")
def api_agents_list():
    return {"agents": manager.list()}

@app.post("/api/agents/start")
async def api_agents_start_all():
    if int(kill_switch._value.get()) == 1:
        raise HTTPException(409, "Kill switch enabled")
    await manager.start_all()
    return {"ok": True}

@app.post("/api/agents/stop")
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

@app.get("/api/status")
def status():
    return {
        "mode": settings.MODE,
        "symbols": settings.ALLOWED_SYMBOLS,
        "maxPosition": settings.MAX_POSITION,
        "orderSize": settings.ORDER_SIZE,
        "kill": int(kill_switch._value.get()),
    }

@app.post("/api/kill")
async def kill(req: Request):
    body = await req.json()
    enabled = bool(body.get("enabled", True))
    kill_switch.set(1 if enabled else 0)
    if enabled:
        await manager.stop_all()
    return {"kill": int(kill_switch._value.get())}

@app.get("/metrics")
def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.get("/api/build")
def build():
    sha = "unknown"
    try:
        sha = subprocess.check_output(["git","rev-parse","--short","HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        pass
    return {"name":"Crypto Agents Pro","version":"stable-v2","git":sha}


# Serve static UI at /ui and redirect root to /ui
app.mount("/ui", StaticFiles(directory=str(Path(__file__).resolve().parents[2] / "web"), html=True), name="ui")

@app.get("/", include_in_schema=False)
def root_redirect():
    return RedirectResponse(url="/ui/")



@app.get("/api/positions")
async def api_positions():
    ex = manager.get_agent("execution")
    if not ex:
        raise HTTPException(404, "Execution agent not found")
    # Pull fresh prices for accurate unrealized PnL
    snap = await ex.snapshot(lambda s: manager.pricefeed.last_price(s, refresh=True))
    return snap

@app.get("/api/pnl")
async def api_pnl():
    ex = manager.get_agent("execution")
    if not ex:
        raise HTTPException(404, "Execution agent not found")
    # Pull fresh prices for accurate unrealized PnL
    snap = await ex.snapshot(lambda s: manager.pricefeed.last_price(s, refresh=True))
    total = snap.get("pnl_realized_day", 0.0) + snap.get("pnl_unrealized", 0.0)
    return {
        "realized_day": snap.get("pnl_realized_day", 0.0),
        "unrealized": snap.get("pnl_unrealized", 0.0),
        "total": total,
        "by_symbol": snap.get("by_symbol", {}),
    }

@app.get("/api/trades")
def api_trades(limit: int = 100):
    ex = manager.get_agent("execution")
    if not ex:
        raise HTTPException(404, "Execution agent not found")
    return {"trades": ex.recent_trades(limit)}

