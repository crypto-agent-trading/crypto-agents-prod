import asyncio, logging
from typing import List, Dict, Any, Optional

class BaseAgent:
    def __init__(self, name: str, symbols: List[str], mode: str = "paper", config: Optional[Dict[str, Any]] = None):
        self.name = name
        self.symbols = symbols
        self.mode = mode
        self.config = config or {}
        self._task: Optional[asyncio.Task] = None
        self._running = asyncio.Event()
        self.status = "idle"  # idle|running|stopping|error
        self.log = logging.getLogger(f"agent.{name}")

    async def start(self):
        if self._task and not self._task.done():
            return
        self._running.set()
        self.status = "running"
        self._task = asyncio.create_task(self._runner())

    async def stop(self):
        self._running.clear()
        self.status = "stopping"
        if self._task:
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except asyncio.TimeoutError:
                self.log.warning("Force stopping agent %s", self.name)
        self.status = "idle"

    async def _runner(self):
        try:
            await self.run()
        except asyncio.CancelledError:
            pass
        except Exception:
            self.status = "error"
            self.log.exception("Agent %s crashed", self.name)
        finally:
            if self.status != "error":
                self.status = "idle"

    async def run(self):
        raise NotImplementedError
