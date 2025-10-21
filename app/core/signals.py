# app/core/signals.py
import asyncio
from dataclasses import dataclass
from typing import List, Tuple, Optional

@dataclass
class Signal:
    symbol: str
    side: str          # "buy" or "sell"
    qty: float
    reason: str
    ts: float

class SignalBus:
    """
    Cross-loop safe pub/sub for Signal objects.
    Each subscriber gets its own asyncio.Queue bound to the loop it subscribed from.
    publish() detects loop differences and uses run_coroutine_threadsafe when needed.
    """
    def __init__(self) -> None:
        self._subs: List[Tuple[asyncio.Queue, Optional[asyncio.AbstractEventLoop]]] = []
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        async with self._lock:
            self._subs.append((q, loop))
        return q

    async def unsubscribe(self, q: asyncio.Queue) -> None:
        async with self._lock:
            self._subs = [(qq, lp) for (qq, lp) in self._subs if qq is not q]

    async def publish(self, sig: Signal) -> None:
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        stale: List[Tuple[asyncio.Queue, Optional[asyncio.AbstractEventLoop]]] = []
        for q, loop in list(self._subs):
            try:
                if current_loop is loop:
                    q.put_nowait(sig)
                else:
                    asyncio.run_coroutine_threadsafe(q.put(sig), loop)  # type: ignore[arg-type]
            except Exception:
                stale.append((q, loop))

        if stale:
            async with self._lock:
                self._subs = [(q, lp) for (q, lp) in self._subs if (q, lp) not in stale]
