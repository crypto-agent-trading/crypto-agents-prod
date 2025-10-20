import asyncio, time
from .base import BaseAgent
from typing import Any
from ..core.signals import Signal, SignalBus

class MarketScannerAgent(BaseAgent):
    def __init__(self, pricefeed: Any, bus: SignalBus, **kwargs):
        super().__init__(**kwargs)
        self.pricefeed = pricefeed
        self.bus = bus
        self._last = {}

    async def run(self):
        interval = float(self.config.get("interval_sec", 2))
        mom_thresh = float(self.config.get("mom_thresh", 0.25))
        qty = float(self.config.get("qty", 1))
        while self._running.is_set():
            for sym in self.symbols:
                try:
                    price = await self.pricefeed.last_price(sym)
                    prev = self._last.get(sym, price)
                    mom = price - prev
                    self._last[sym] = price
                    if abs(mom) >= mom_thresh:
                        side = "buy" if mom > 0 else "sell"
                        await self.bus.publish(Signal(symbol=sym, side=side, qty=qty, reason=f"momentum {mom:.3f}", ts=time.time()))
                        self.log.info(f"[scanner] signal {side} {sym} mom={mom:.3f}")
                except Exception:
                    self.log.exception("scanner error")
            await asyncio.sleep(interval)
