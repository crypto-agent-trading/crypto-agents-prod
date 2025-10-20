import json, asyncio
from pathlib import Path
from typing import Dict, Any, List
from .market_scanner import MarketScannerAgent
from .depth import DepthL1L3Agent
from .execution import ExecutionAgent
from .indicator import IndicatorAgent
from ..services.pricefeed import PriceFeed
from ..services.kraken_ws import KrakenWS
from ..exchanges.paper import PaperExchange
from ..exchanges.kraken import KrakenExchange
from ..core.config import settings, is_live
from ..core.signals import SignalBus

AGENT_TYPES = {
    "market_scanner": MarketScannerAgent,
    "depth_l1l3": DepthL1L3Agent,
    "execution": ExecutionAgent,
    "indicator": IndicatorAgent,
}

class AgentManager:
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / "agents_state.json"
        self._agents: Dict[str, Any] = {}
        self._configs: Dict[str, Dict[str, Any]] = {}

        if is_live():
            ex = KrakenExchange(settings.KRAKEN_API_KEY, settings.KRAKEN_API_SECRET, mode="live")
        else:
            ex = PaperExchange(mode="paper")
        self.exchange = ex
        self.pricefeed = PriceFeed(ex)
        self.bus = SignalBus()

        self._ws = None
        if settings.FEED_MODE == "ws":
            self._ws = KrakenWS()
            for sym in settings.ALLOWED_SYMBOLS:
                asyncio.create_task(self._ws.subscribe_ticker(sym, lambda p, s=sym: self.pricefeed.inject_price(s, p)))

    def _save(self):
        data = {"agents": list(self._configs.values())}
        self.state_file.write_text(json.dumps(data, indent=2))

    def _load(self):
        if self.state_file.exists():
            data = json.loads(self.state_file.read_text())
            self._configs = {cfg["name"]: cfg for cfg in data.get("agents", [])}

    def upsert(self, cfg: Dict[str, Any]):
        name = cfg["name"]
        self._configs[name] = cfg
        self._save()

    def build_all(self):
        self._load()
        for name, cfg in self._configs.items():
            if name in self._agents:
                continue
            cls = AGENT_TYPES[cfg["type"]]
            common = dict(name=cfg["name"], symbols=cfg["symbols"], mode=settings.MODE, config=cfg.get("config", {}))
            if cls.__name__ in ("MarketScannerAgent", "DepthL1L3Agent", "IndicatorAgent"):
                self._agents[name] = cls(pricefeed=self.pricefeed, bus=self.bus, **common)
            elif cls.__name__ == "ExecutionAgent":
                self._agents[name] = cls(exchange=self.exchange, bus=self.bus, **common)
            else:
                self._agents[name] = cls(**common)

    def get_agent(self, name: str):
        return self._agents.get(name)

    def list(self) -> List[Dict[str, Any]]:
        out = []
        for name, agent in self._agents.items():
            out.append({
                "name": name,
                "type": self._configs[name]["type"],
                "symbols": agent.symbols,
                "mode": agent.mode,
                "status": agent.status,
                "config": agent.config
            })
        return out

    async def start(self, name: str):
        await self._agents[name].start()

    async def stop(self, name: str):
        await self._agents[name].stop()

    async def start_all(self):
        for n in self._agents:
            await self.start(n)

    async def stop_all(self):
        for n in self._agents:
            await self.stop(n)
