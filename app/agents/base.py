# app/agents/base.py
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger("agent.base")

class BaseAgent:
    """
    Common lifecycle for all agents:
      - start(): sets running flag and spawns a background task
      - stop(): clears flag and cancels the task
      - status: 'running' or 'stopped'
    Subclasses must implement async def run(self).
    """

    def __init__(self, name: str, symbols: List[str], mode: str, config: Dict[str, Any]):
        self.name = name
        self.symbols = symbols or []
        self.mode = mode
        self.config = config or {}
        self._running = asyncio.Event()
        self._task: Optional[asyncio.Task] = None

    @property
    def status(self) -> str:
        return "running" if (self._task and not self._task.done() and self._running.is_set()) else "stopped"

    async def start(self):
        if self._task and not self._task.done():
            log.info("[%s] already running", self.name)
            return
        self._running.set()
        self._task = asyncio.create_task(self._run_wrapper(), name=f"{self.name}-task")
        log.info("[%s] started (symbols=%s)", self.name, ",".join(self.symbols) or "<none>")

    async def stop(self):
        self._running.clear()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("[%s] stopped", self.name)

    async def _run_wrapper(self):
        try:
            await self.run()
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("[%s] crashed", self.name)
        finally:
            self._running.clear()

    async def run(self):
        """Subclasses implement the main loop."""
        raise NotImplementedError
