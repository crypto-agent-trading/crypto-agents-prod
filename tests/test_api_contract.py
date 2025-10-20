import time
from fastapi.testclient import TestClient
from app.api.main import app

client = TestClient(app)

def _assert_keys(obj, keys):
    for k in keys:
        assert k in obj, f"missing key: {k}"

def test_build_and_status():
    r = client.get("/api/build")
    assert r.status_code == 200
    _assert_keys(r.json(), ["name", "version", "git"])

    r = client.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    _assert_keys(body, ["mode", "symbols", "maxPosition", "orderSize", "kill"])
    assert isinstance(body["symbols"], list)

def test_agents_list_and_lifecycle():
    r = client.get("/api/agents")
    assert r.status_code == 200
    body = r.json()
    assert "agents" in body
    names = [a["name"] for a in body["agents"]]
    assert {"market-scanner","depth-l1l3","indicator","execution"} <= set(names)

    # start/stop all
    r = client.post("/api/agents/start"); assert r.status_code == 200
    time.sleep(1.0)  # give agents a tick
    r = client.post("/api/agents/stop");  assert r.status_code == 200

def test_contract_positions_pnl_trades():
    client.post("/api/agents/start")
    time.sleep(1.0)

    r = client.get("/api/positions")
    assert r.status_code == 200
    pos = r.json()
    _assert_keys(pos, ["by_symbol","pnl_realized_day","pnl_unrealized"])
    assert isinstance(pos["by_symbol"], dict)

    r = client.get("/api/pnl")
    assert r.status_code == 200
    pnl = r.json()
    _assert_keys(pnl, ["realized_day","unrealized","total","by_symbol"])
    assert isinstance(pnl["by_symbol"], dict)

    r = client.get("/api/trades?limit=5")
    assert r.status_code == 200
    trades = r.json()["trades"]
    assert isinstance(trades, list)
    if trades:
        _assert_keys(trades[0], ["ts","symbol","side","qty","price","position_after","avg_price_after","realized_change"])

    client.post("/api/agents/stop")
