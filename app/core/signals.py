import asyncio
from dataclasses import dataclass
from typing import Optional

@dataclass
class Signal:
    symbol: str
    side: str     # "buy" | "sell"
    qty: float
    reason: str
    ts: float

class SignalBus:
    def __init__(self):
        self._q: asyncio.Queue[Signal] = asyncio.Queue(maxsize=1000)

    async def publish(self, sig: Signal):
        await self._q.put(sig)

    async def subscribe(self) -> asyncio.Queue:
        return self._q
