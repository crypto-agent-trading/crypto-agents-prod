import asyncio, json, websockets
from typing import Callable

KRAKEN_WS = "wss://ws.kraken.com/v2"

class KrakenWS:
    def __init__(self):
        self._tasks = []

    async def subscribe_ticker(self, symbol: str, on_tick: Callable[[float], None]):
        async def _runner():
            msg = {"method":"subscribe", "params":{"channel":"ticker","symbol":[symbol]}}
            async with websockets.connect(KRAKEN_WS, ping_interval=20) as ws:
                await ws.send(json.dumps(msg))
                async for raw in ws:
                    try:
                        data = json.loads(raw)
                        if isinstance(data, dict) and data.get("channel") == "ticker":
                            price = data.get("price")
                            if price:
                                on_tick(float(price))
                    except Exception:
                        pass
        self._tasks.append(asyncio.create_task(_runner()))

    async def stop(self):
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()
