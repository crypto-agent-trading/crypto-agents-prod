# app/agents/manager.py
from __future__ import annotations

import asyncio, json, logging
from pathlib import Path
from typing import Dict, Any, List

from .market_scanner import MarketScannerAgent
from .depth import DepthL1L3Agent
from .indicator import IndicatorAgent
from .execution import ExecutionAgent

from ..services.pricefeed import PriceFeed
from ..exchanges.paper import PaperExchange
from ..exchanges.kraken import KrakenExchange
from ..core.config import settings, is_live
from ..core.signals import SignalBus
from ..core.state import Portfolio

log = logging.getLogger("agents.manager")

class AgentManager:
    def __init__(self, config_path: Path | None = None):
        self._cfg_path = config_path or Path("agents.json")
        self._agents: Dict[str, Any] = {}
        self._agent_cfgs: Dict[str, Dict[str, Any]] = {}

        self.bus = SignalBus()
        self.exchange = KrakenExchange() if is_live() else PaperExchange()
        self.pricefeed = PriceFeed(self.exchange)
        self.portfolio = Portfolio(self.pricefeed)

        if not self._cfg_path.exists():
            default = {
                "market_scanner": {"enabled": False, "interval_sec": 2, "mom_thresh": 0.25},
                "depth":          {"enabled": False, "interval_sec": 3, "imbalance_thresh": 0.60},
                "indicator":      {"enabled": True,  "interval_sec": 2},
                "execution":      {"enabled": True}
            }
            self._cfg_path.write_text(json.dumps(default, indent=2))
        self._agent_cfgs = json.loads(self._cfg_path.read_text())

        self.build_all()

    def build_all(self):
        syms = list(settings.ALLOWED_SYMBOLS or []) or ["BTC/CAD", "ETH/CAD"]
        mode = settings.MODE

        cfg = self._agent_cfgs
        self._agents.clear()

        if cfg.get("market_scanner", {}).get("enabled"):
            self._agents["market_scanner"] = MarketScannerAgent(
                name="market_scanner", symbols=syms, mode=mode, config=cfg["market_scanner"],
                pricefeed=self.pricefeed, bus=self.bus
            )
        if cfg.get("depth", {}).get("enabled"):
            self._agents["depth"] = DepthL1L3Agent(
                name="depth", symbols=syms, mode=mode, config=cfg["depth"],
                pricefeed=self.pricefeed, bus=self.bus
            )
        if cfg.get("indicator", {}).get("enabled", True):
            self._agents["indicator"] = IndicatorAgent(
                name="indicator", symbols=syms, mode=mode, config=cfg["indicator"],
                pricefeed=self.pricefeed, bus=self.bus
            )
        if cfg.get("execution", {}).get("enabled", True):
            self._agents["execution"] = ExecutionAgent(
                name="execution", symbols=syms, mode=mode, config=cfg["execution"],
                exchange=self.exchange, pricefeed=self.pricefeed, bus=self.bus,
                portfolio=self.portfolio
            )

        log.info("Built agents: %s", ",".join(self._agents.keys()) or "<none>")
        log.info("Symbols: %s | mode=%s | live=%s", ",".join(syms), mode, is_live())

    def list(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for n, ag in self._agents.items():
            out.append({"name": n, "status": ag.status, "mode": ag.mode, "symbols": ag.symbols, "config": ag.config})
        return out

    async def start(self, name: str):
        ag = self._agents.get(name)
        if ag:
            await ag.start()

    async def stop(self, name: str):
        ag = self._agents.get(name)
        if ag:
            await ag.stop()

    async def start_all(self):
        for _, ag in self._agents.items():
            await ag.start()
        log.info("All agents started: %s", ",".join(self._agents.keys()))

    async def stop_all(self):
        for _, ag in self._agents.items():
            await ag.stop()
        log.info("All agents stopped")
