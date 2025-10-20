import asyncio, ccxt
from typing import Dict, Any, List
from .base import Exchange

class KrakenExchange(Exchange):
    def __init__(self, api_key: str, api_secret: str, mode: str = "live"):
        self.mode = mode
        self.client = ccxt.kraken({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
        })

    async def _call(self, fn, *args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))

    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        return await self._call(self.client.fetch_ticker, symbol)

    async def fetch_order_book(self, symbol: str) -> Dict[str, Any]:
        return await self._call(self.client.fetch_order_book, symbol)

    async def create_order(self, symbol: str, side: str, qty: float, price: float | None = None, client_id: str | None = None) -> Dict[str, Any]:
        params = {}
        if client_id:
            params["userref"] = client_id  # kraken-specific idempotency-ish
        if price:
            order = await self._call(self.client.create_limit_order, symbol, side, qty, price, params)
        else:
            order = await self._call(self.client.create_market_order, symbol, side, qty, params)
        return order

    async def fetch_open_orders(self, symbol: str) -> List[Dict[str, Any]]:
        return await self._call(self.client.fetch_open_orders, symbol)

    async def cancel_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        return await self._call(self.client.cancel_order, order_id, symbol)

    async def fetch_balance(self) -> Dict[str, Any]:
        return await self._call(self.client.fetch_balance)
