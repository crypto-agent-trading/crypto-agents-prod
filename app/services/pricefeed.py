# app/services/pricefeed.py
from __future__ import annotations
import asyncio
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from ..core.config import settings

log = logging.getLogger("services.pricefeed")

def _map_ohlcv_rows(rows: List[List[float]]) -> List[Dict[str, float]]:
    out: List[Dict[str, float]] = []
    for r in rows or []:
        # CCXT OHLCV: [timestamp, open, high, low, close, volume]
        ts, o, h, l, c, v = (r + [None] * 6)[:6]
        out.append({"ts": float(ts or 0), "open": float(o), "high": float(h), "low": float(l), "close": float(c), "volume": float(v)})
    return out

class PriceFeed:
    """
    Thin async wrapper around the exchange for public market data.
    Works in PAPER or LIVE. If the exchange doesn't implement public fetches,
    we attempt to fall back to its 'public' client (ccxt) when available.
    """

    def __init__(self, exchange) -> None:
        self.exchange = exchange

    async def _maybe_await(self, coro_or_val):
        if asyncio.iscoroutine(coro_or_val):
            return await coro_or_val
        # allow sync fallbacks via threads to avoid blocking loop
        return await asyncio.to_thread(lambda: coro_or_val)

    async def get_orderbook(self, symbol: str, limit: int = 5) -> Dict[str, Any]:
        # try exchange.fetch_order_book
        if hasattr(self.exchange, "fetch_order_book"):
            ob = await self._maybe_await(self.exchange.fetch_order_book(symbol, limit=limit))
            if ob and ob.get("bids") and ob.get("asks"):
                return {"bids": ob["bids"], "asks": ob["asks"], "ts": ob.get("timestamp")}
        # try exchange.public.fetch_order_book
        public = getattr(self.exchange, "public", None)
        if public and hasattr(public, "fetch_order_book"):
            ob = await self._maybe_await(public.fetch_order_book(symbol, limit=limit))
            return {"bids": ob.get("bids", []), "asks": ob.get("asks", []), "ts": ob.get("timestamp")}
        # last resort
        log.warning("[pricefeed] empty orderbook for %s", symbol)
        return {"bids": [], "asks": [], "ts": None}

    async def get_recent_klines(self, symbol: str, timeframe: str = "1m", limit: int = 300) -> List[Dict[str, float]]:
        # try exchange.fetch_ohlcv
        if hasattr(self.exchange, "fetch_ohlcv"):
            rows = await self._maybe_await(self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=None, limit=limit))
            if rows:
                return _map_ohlcv_rows(rows)
        # try exchange.public.fetch_ohlcv
        public = getattr(self.exchange, "public", None)
        if public and hasattr(public, "fetch_ohlcv"):
            rows = await self._maybe_await(public.fetch_ohlcv(symbol, timeframe=timeframe, since=None, limit=limit))
            return _map_ohlcv_rows(rows)
        # last resort
        log.warning("[pricefeed] empty ohlcv for %s", symbol)
        return []
