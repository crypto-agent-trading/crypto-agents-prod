import asyncio, random
from typing import List, Dict, Any
from ..exchanges.base import Exchange

class PriceFeed:
    def __init__(self, exchange: Exchange):
        self.exchange = exchange
        self._last: dict[str, float] = {}

    def inject_price(self, symbol: str, price: float):
        self._last[symbol] = price

    async def last_price(self, symbol: str) -> float:
        if symbol in self._last:
            return float(self._last[symbol])
        t = await self.exchange.fetch_ticker(symbol)
        price = t.get("last") or t.get("close") or t.get("info", {}).get("c", [None])[0]
        if price is None:
            ob = await self.exchange.fetch_order_book(symbol)
            price = (ob["bids"][0][0] + ob["asks"][0][0]) / 2.0
        self._last[symbol] = float(price)
        return float(price)

    async def get_recent_klines(self, symbol: str, limit: int = 50) -> List[Dict[str, Any]]:
        p = await self.last_price(symbol)
        candles = []
        v = p
        for i in range(limit):
            v *= (1 + random.uniform(-0.002, 0.002))
            candles.append({"close": v})
        return candles

    async def get_orderbook(self, symbol: str) -> Dict[str, Any]:
        return await self.exchange.fetch_order_book(symbol)
