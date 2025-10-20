import asyncio, time, uuid
from typing import Any, Dict, Deque, List
from collections import deque

from .base import BaseAgent
from ..core.config import settings
from ..core.metrics import (
    orders_placed, orders_filled, orders_rejected,
    positions_gauge, kill_switch
)
from ..core.signals import Signal

class ExecutionAgent(BaseAgent):
    """
    Consumes signals, enforces risk, sends orders, records trades,
    maintains positions/avg price, and tracks realized day PnL.
    """
    def __init__(self, exchange: Any, bus, **kwargs):
        super().__init__(**kwargs)
        self.exchange = exchange
        self.bus = bus
        self.positions: Dict[str, float] = {}
        self.avg_price: Dict[str, float] = {}
        self.realized_pnl_day: float = 0.0
        self.trades: Deque[Dict[str, Any]] = deque(maxlen=1000)
        self._recon_task: asyncio.Task | None = None

    # ---------- Risk ----------
    def _check_risk(self, symbol: str, side: str, qty: float):
        pos = self.positions.get(symbol, 0.0)
        if settings.LONG_ONLY and side == "sell" and pos <= 0:
            raise ValueError("LONG_ONLY enabled; cannot sell without position")
        if abs(pos + (qty if side == "buy" else -qty)) > float(settings.MAX_POSITION):
            raise ValueError("max position exceeded")
        if self.realized_pnl_day <= -abs(settings.MAX_DAILY_LOSS):
            raise ValueError("daily loss limit exceeded")

    # ---------- State updates ----------
    def _apply_fill(self, symbol: str, side: str, qty: float, price: float):
        pos = self.positions.get(symbol, 0.0)
        avg = self.avg_price.get(symbol, 0.0)
        realized_change = 0.0

        if side == "buy":
            new_pos = pos + qty
            new_avg = (avg * pos + price * qty) / max(new_pos, 1e-9)
            self.positions[symbol] = new_pos
            self.avg_price[symbol] = new_avg
        else:  # sell
            close_qty = min(qty, pos) if pos > 0 else qty
            realized_change = (price - avg) * close_qty
            self.realized_pnl_day += realized_change
            self.positions[symbol] = max(pos - qty, 0.0)
            if self.positions[symbol] == 0:
                self.avg_price[symbol] = 0.0

        positions_gauge.labels(symbol, self.mode).set(self.positions.get(symbol, 0.0))
        self.trades.append({
            "ts": time.time(),
            "symbol": symbol,
            "side": side,
            "qty": float(qty),
            "price": float(price),
            "position_after": float(self.positions.get(symbol, 0.0)),
            "avg_price_after": float(self.avg_price.get(symbol, 0.0)),
            "realized_change": float(realized_change),
        })

    # ---------- Order send ----------
    async def _market(self, symbol: str, side: str, qty: float):
        # Soft skip when LONG_ONLY and flat
        if settings.LONG_ONLY and side == "sell" and self.positions.get(symbol, 0.0) <= 0:
            self.log.info("[exec] skip sell %s (LONG_ONLY, flat)", symbol)
            return

        client_id = str(uuid.uuid4())[:12]
        try:
            self._check_risk(symbol, side, qty)
            orders_placed.labels(symbol, side, self.mode).inc()
            res = await self.exchange.create_order(symbol, side, qty, price=None, client_id=client_id)

            price = res.get("price") or res.get("average") or res.get("info", {}).get("price") or 0.0
            price = float(price or 0.0)

            if res.get("status") in ("closed", "filled", "success") or price > 0:
                self._apply_fill(symbol, side, qty, price)
                orders_filled.labels(symbol, side, self.mode).inc()
                self.log.info("[exec] filled %s %s %s @ %.2f pnl_day=%.2f",
                              side, qty, symbol, price, self.realized_pnl_day)
            else:
                orders_rejected.labels(symbol, side, self.mode).inc()
                self.log.warning("[exec] order not filled: %s", res)

        except Exception as e:
            orders_rejected.labels(symbol, side, self.mode).inc()
            self.log.exception("execution error")
            if "daily loss limit exceeded" in str(e).lower():
                kill_switch.set(1)
                await self.stop()

    # ---------- Housekeeping ----------
    async def _reconcile_loop(self):
        while self._running.is_set():
            try:
                for sym in self.symbols:
                    _ = await self.exchange.fetch_open_orders(sym)
                await asyncio.sleep(10)
            except Exception:
                self.log.exception("reconcile error")
                await asyncio.sleep(10)

    async def start(self):
        await super().start()
        if not self._recon_task or self._recon_task.done():
            self._recon_task = asyncio.create_task(self._reconcile_loop())

    async def stop(self):
        if self._recon_task:
            self._recon_task.cancel()
        await super().stop()

    # ---------- Run (consume signals) ----------
    async def run(self):
        q = await self.bus.subscribe()
        while self._running.is_set():
            try:
                sig: Signal = await asyncio.wait_for(q.get(), timeout=1.0)
                await self._market(sig.symbol, sig.side, float(settings.ORDER_SIZE))
            except asyncio.TimeoutError:
                continue
            except Exception:
                self.log.exception("execution run loop error")

    # ---------- API helpers ----------
    async def snapshot(self, price_fetcher) -> Dict[str, Any]:
        data = {}
        total_unreal = 0.0
        for sym, pos in self.positions.items():
            last = float(await price_fetcher(sym))
            if pos == 0:
                data[sym] = {"position": 0.0, "avg_price": 0.0, "last": last, "unrealized": 0.0}
                continue
            avg = float(self.avg_price.get(sym, 0.0))
            unreal = (last - avg) * pos
            total_unreal += unreal
            data[sym] = {"position": float(pos), "avg_price": avg, "last": last, "unrealized": float(unreal)}
        return {"by_symbol": data, "pnl_realized_day": float(self.realized_pnl_day), "pnl_unrealized": float(total_unreal)}

    def recent_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
        return list(self.trades)[-limit:] if limit > 0 else []
