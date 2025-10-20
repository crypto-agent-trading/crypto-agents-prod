# Crypto Agents Pro (Stable v2)

**Important:** Trading crypto involves substantial risk. This project defaults to **paper** mode.
Switch to **live** only after thorough testing. No profit is guaranteed.

## Features
- Agent framework (scanner, depth, indicator, execution)
- Paper vs Live switch via `.env`
- Minimal **signal bus** (scanner/depth/indicator → execution)
- Risk controls: symbol whitelist, max position/order, per-trade risk %, daily loss limit, kill switch
- Idempotent orders with client refs and reconciliation loop (basic)
- Persistence of agent configs/state (`data/agents_state.json`)
- FastAPI management API + Prometheus metrics (`/metrics`)
- Structured JSON logging with rotating files
- Typer CLI to manage server/agents
- Pinned dependencies
- Dockerfile + docker-compose
- Optional Kraken **WebSocket** price updates (skeleton), fallback to REST

## Quickstart (Windows PowerShell)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt

# copy .env.example to .env and fill in your keys (if going live)
Copy-Item .env.example .env

# run API (no reload for stability)
python -m uvicorn app.api.main:app --host 0.0.0.0 --port 8000

# or use the CLI
python manage.py server
```

## .env
```
MODE=paper                   # paper or live
ALLOWED_SYMBOLS=["BTC/CAD","ETH/CAD"]   # JSON array (not CSV)
MAX_POSITION=50
ORDER_SIZE=10
PER_TRADE_RISK_PCT=0.01
MAX_DAILY_LOSS=100
FEED_MODE=rest              # rest or ws
LONG_ONLY=true              # true/false (spot trading safest)
KRAKEN_API_KEY=your_key_here
KRAKEN_API_SECRET=your_secret_here
LOG_LEVEL=INFO
```

## API Endpoints
- `GET /api/agents` — list agents
- `POST /api/agents/start` — start all
- `POST /api/agents/stop` — stop all
- `POST /api/agents/start/{name}` — start one
- `POST /api/agents/stop/{name}` — stop one
- `POST /api/kill` — set kill switch `{ "enabled": true }`
- `GET /api/status` — status snapshot
- `GET /metrics` — Prometheus metrics
```

## Notes
- Keep `MODE=paper` until your signals & risk model are proven.
- Never hardcode API keys; use `.env` only.
