import asyncio, time
from .base import BaseAgent
from typing import Any, List, Dict
from ..core.signals import Signal, SignalBus

def rsi(closes: List[float], period: int = 14) -> float:
    if len(closes) < period+1: return 50.0
    gains = []
    losses = []
    for i in range(-period, 0):
        d = closes[i] - closes[i-1]
        gains.append(max(d, 0))
        losses.append(abs(min(d, 0)))
    avg_gain = sum(gains)/period
    avg_loss = (sum(losses)/period) or 1e-9
    rs = avg_gain/avg_loss
    return 100 - (100/(1+rs))

class IndicatorAgent(BaseAgent):
    def __init__(self, pricefeed: Any, bus: SignalBus, **kwargs):
        super().__init__(**kwargs)
        self.pricefeed = pricefeed
        self.bus = bus
        self._prev_rsi = {}

    async def run(self):
        interval = float(self.config.get("interval_sec", 3))
        rsi_period = int(self.config.get("rsi_period", 14))
        buy_th = float(self.config.get("rsi_buy", 55))
        sell_th = float(self.config.get("rsi_sell", 45))
        qty = float(self.config.get("qty", 1))
        while self._running.is_set():
            for sym in self.symbols:
                try:
                    candles: List[Dict] = await self.pricefeed.get_recent_klines(sym, limit=50)
                    closes = [c["close"] for c in candles]
                    val = rsi(closes, rsi_period)
                    prev = self._prev_rsi.get(sym, val)
                    if prev < buy_th <= val:
                        await self.bus.publish(Signal(sym, "buy", qty, f"rsi cross {prev:.1f}->{val:.1f}", time.time()))
                        self.log.info(f"[indicator] buy {sym} rsi={val:.1f}")
                    elif prev > sell_th >= val:
                        await self.bus.publish(Signal(sym, "sell", qty, f"rsi cross {prev:.1f}->{val:.1f}", time.time()))
                        self.log.info(f"[indicator] sell {sym} rsi={val:.1f}")
                    self._prev_rsi[sym] = val
                except Exception:
                    self.log.exception("indicator error")
            await asyncio.sleep(interval)
