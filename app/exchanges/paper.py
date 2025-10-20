import asyncio, time, uuid, random
from typing import Dict, Any, List
from .base import Exchange

class PaperExchange(Exchange):
    def __init__(self, mode: str = "paper"):
        self.mode = mode
        self.last_price: Dict[str, float] = {}
        self.positions: Dict[str, float] = {}
        self.pnl: Dict[str, float] = {}
        self.open_orders: Dict[str, Dict[str, Any]] = {}
        # Simulated microstructure to make PnL realistic
        self.spread = 0.10     # ~10 cents around mid
        self.slippage = 0.02   # small extra impact

    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        price = self.last_price.get(symbol, 100.0)
        # tiny random walk so unrealized PnL moves
        price *= (1 + random.uniform(-0.001, 0.001))
        self.last_price[symbol] = price
        return {"symbol": symbol, "last": price, "timestamp": int(time.time() * 1000)}

    async def fetch_order_book(self, symbol: str) -> Dict[str, Any]:
        p = self.last_price.get(symbol, 100.0)
        bid = p - self.spread / 2
        ask = p + self.spread / 2
        return {"bids": [[bid, 1.0]], "asks": [[ask, 1.0]]}

    async def create_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float | None = None,
        client_id: str | None = None,
    ) -> Dict[str, Any]:
        """
        Simulate immediate marketable fill with bid/ask and small slippage.
        """
        oid = client_id or str(uuid.uuid4())
        last = self.last_price.get(symbol, 100.0)
        bid = last - self.spread / 2
        ask = last + self.spread / 2
        side_l = side.lower()

        if side_l == "buy":
            base = ask if price is None else price
            fill_price = float(base + random.uniform(0, self.slippage))
            signed_qty = qty
        else:
            base = bid if price is None else price
            fill_price = float(base - random.uniform(0, self.slippage))
            signed_qty = -qty

        self.positions[symbol] = self.positions.get(symbol, 0.0) + signed_qty
        self.open_orders.pop(oid, None)
        return {
            "id": oid,
            "symbol": symbol,
            "side": side,
            "status": "filled",
            "filled": abs(qty),
            "price": fill_price,
        }

    async def fetch_open_orders(self, symbol: str) -> List[Dict[str, Any]]:
        return [o for o in self.open_orders.values() if o["symbol"] == symbol]

    async def cancel_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        self.open_orders.pop(order_id, None)
        return {"id": order_id, "status": "canceled"}

    async def fetch_balance(self) -> Dict[str, Any]:
        return {"free": {"CAD": 100000.0}, "total": {"CAD": 100000.0}}
