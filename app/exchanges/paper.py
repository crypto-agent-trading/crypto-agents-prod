import asyncio, time, uuid, random
from typing import Dict, Any, List
from .base import Exchange

class PaperExchange(Exchange):
    def __init__(self, mode: str = "paper"):
        self.mode = mode
        self.last_price = {}  # symbol -> float
        self.positions = {}   # symbol -> float
        self.pnl = {}         # symbol -> float
        self.open_orders: Dict[str, Dict[str, Any]] = {}

    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        price = self.last_price.get(symbol, 100.0)
        # small random walk to simulate market
        price *= (1 + random.uniform(-0.001, 0.001))
        self.last_price[symbol] = price
        return {"symbol": symbol, "last": price, "timestamp": int(time.time()*1000)}

    async def fetch_order_book(self, symbol: str) -> Dict[str, Any]:
        p = self.last_price.get(symbol, 100.0)
        return {"bids": [[p-0.1, 1.0]], "asks": [[p+0.1, 1.0]]}

    async def create_order(self, symbol: str, side: str, qty: float, price: float | None = None, client_id: str | None = None) -> Dict[str, Any]:
        # market order simulation (immediate fill at last price)
        oid = client_id or str(uuid.uuid4())
        last = self.last_price.get(symbol, 100.0)
        fill_price = price or last
        signed_qty = qty if side.lower() == "buy" else -qty
        self.positions[symbol] = self.positions.get(symbol, 0.0) + signed_qty
        self.open_orders.pop(oid, None)
        return {"id": oid, "symbol": symbol, "side": side, "status": "filled", "filled": abs(qty), "price": fill_price}

    async def fetch_open_orders(self, symbol: str) -> List[Dict[str, Any]]:
        return [o for o in self.open_orders.values() if o["symbol"] == symbol]

    async def cancel_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        self.open_orders.pop(order_id, None)
        return {"id": order_id, "status": "canceled"}

    async def fetch_balance(self) -> Dict[str, Any]:
        return {"free": {"CAD": 100000.0}, "total": {"CAD": 100000.0}}
