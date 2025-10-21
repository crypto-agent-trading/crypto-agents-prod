# app/agents/manager.py
import asyncio, json
from pathlib import Path
from typing import Dict, Any, List, Optional

from .market_scanner import MarketScannerAgent
from .depth import DepthL1L3Agent
from .indicator import IndicatorAgent
from .execution import ExecutionAgent

from ..services.pricefeed import PriceFeed
from ..exchanges.paper import PaperExchange
from ..exchanges.kraken import KrakenExchange
from ..core.config import settings, is_live
from ..core.signals import SignalBus

class AgentManager:
    """
    Builds and manages all agents, wiring them with a shared SignalBus.
    """

    def __init__(self, config_path: Path | None = None):
        self._cfg_path = config_path or Path("agents.json")
        self._agents: Dict[str, Any] = {}
        self._agent_cfgs: Dict[str, Dict[str, Any]] = {}
        self.bus = SignalBus()
        self.exchange = KrakenExchange() if is_live() else PaperExchange()
        self.pricefeed = PriceFeed(self.exchange)

        # default config
        if not self._cfg_path.exists():
            default = {
                "market_scanner": {"enabled": False, "interval_sec": 2, "mom_thresh": 0.25, "qty": settings.ORDER_SIZE},
                "depth":          {"enabled": False, "interval_sec": 3, "imbalance_thresh": 0.60, "qty": settings.ORDER_SIZE},
                "indicator":      {"enabled": True,  "interval_sec": 2, "qty": settings.ORDER_SIZE},
                "execution":      {"enabled": True}
            }
            self._cfg_path.write_text(json.dumps(default, indent=2))
        self._agent_cfgs = json.loads(self._cfg_path.read_text())

        # build initial set
        self.build_all()

    def build_all(self):
        syms = settings.ALLOWED_SYMBOLS
        cfg = self._agent_cfgs

        self._agents.clear()
        if cfg.get("market_scanner", {}).get("enabled"):
            self._agents["market_scanner"] = MarketScannerAgent(
                name="market_scanner", symbols=syms, mode=settings.MODE, config=cfg["market_scanner"],
                pricefeed=self.pricefeed, bus=self.bus
            )
        if cfg.get("depth", {}).get("enabled"):
            self._agents["depth"] = DepthL1L3Agent(
                name="depth", symbols=syms, mode=settings.MODE, config=cfg["depth"],
                pricefeed=self.pricefeed, bus=self.bus
            )
        if cfg.get("indicator", {}).get("enabled", True):
            self._agents["indicator"] = IndicatorAgent(
                name="indicator", symbols=syms, mode=settings.MODE, config=cfg["indicator"],
                pricefeed=self.pricefeed, bus=self.bus
            )
        if cfg.get("execution", {}).get("enabled", True):
            self._agents["execution"] = ExecutionAgent(
                name="execution", symbols=syms, mode=settings.MODE, config=cfg["execution"],
                exchange=self.exchange, pricefeed=self.pricefeed, bus=self.bus
            )

    def list(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for n, ag in self._agents.items():
            out.append({"name": n, "status": ag.status, "mode": ag.mode, "symbols": ag.symbols, "config": ag.config})
        return out

    async def start(self, name: str):
        if name in self._agents:
            await self._agents[name].start()

    async def stop(self, name: str):
        if name in self._agents:
            await self._agents[name].stop()

    async def start_all(self):
        for n in list(self._agents.keys()):
            await self.start(n)

    async def stop_all(self):
        for n in list(self._agents.keys()):
            await self.stop(n)

    def update_config(self, name: str, cfg: Dict[str, Any]):
        self._agent_cfgs[name] = cfg
        self._cfg_path.write_text(json.dumps(self._agent_cfgs, indent=2))
        # rebuild agent if needed
        if name in self._agents:
            # stop old
            try:
                asyncio.create_task(self._agents[name].stop())
            except Exception:
                pass
        self.build_all()
