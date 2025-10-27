# app/exchanges/paper.py
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

import ccxt  # sync client is fine for public data; we wrap in to_thread upstream

log = logging.getLogger("exchanges.paper")

class PaperExchange:
    """
    Paper exchange for simulation. Uses CCXT public client for market data.
    Trade methods are simulated elsewhere (your execution agent).
    """
    def __init__(self) -> None:
        # Kraken has CAD & USDT books; change if you prefer another venue
        self.public = ccxt.kraken()
        self.id = "paper-kraken"

    # Optional passthroughs for pricefeed convenience (they may be called via PriceFeed)
    def fetch_order_book(self, symbol: str, limit: int = 5):
        return self.public.fetch_order_book(symbol, limit=limit)

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1m", since=None, limit: int = 300):
        return self.public.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)
