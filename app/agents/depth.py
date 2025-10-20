import asyncio, time
from .base import BaseAgent
from typing import Any
from ..core.signals import Signal, SignalBus

class DepthL1L3Agent(BaseAgent):
    def __init__(self, pricefeed: Any, bus: SignalBus, **kwargs):
        super().__init__(**kwargs)
        self.pricefeed = pricefeed
        self.bus = bus

    async def run(self):
        interval = float(self.config.get("interval_sec", 3))
        th = float(self.config.get("imbalance_thresh", 0.6))
        qty = float(self.config.get("qty", 1))
        while self._running.is_set():
            for sym in self.symbols:
                try:
                    ob = await self.pricefeed.get_orderbook(sym)
                    bid = ob["bids"][0][1] if ob["bids"] else 0
                    ask = ob["asks"][0][1] if ob["asks"] else 0
                    imb = (bid - ask) / max(bid + ask, 1e-6)
                    if imb >= th:
                        await self.bus.publish(Signal(sym, "buy", qty, f"depth imb {imb:.2f}", time.time()))
                        self.log.info(f"[depth] buy {sym} imb={imb:.2f}")
                    elif imb <= -th:
                        await self.bus.publish(Signal(sym, "sell", qty, f"depth imb {imb:.2f}", time.time()))
                        self.log.info(f"[depth] sell {sym} imb={imb:.2f}")
                except Exception:
                    self.log.exception("depth error")
            await asyncio.sleep(interval)
