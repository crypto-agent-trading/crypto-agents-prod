# app/agents/execution.py
# Consumes Signals from SignalBus and executes with post-only limits,
# cancel&reprice, and a realistic PAPER slippage/fee model.

from __future__ import annotations

import asyncio, time, math, logging
from typing import Any, Dict

from .base import BaseAgent
from ..core.config import settings, is_live
from ..core.signals import SignalBus, Signal
from ..services.pricefeed import PriceFeed
from ..exchanges.base import Exchange

log = logging.getLogger("agent.execution")

POST_ONLY_K = 0.3       # place limit at mid -/+ k*spread
REPRICE_SECS = 6.0      # cancel & reprice timeout
REPRICE_MOVE = 0.5      # reprice if adverse move > 0.5*spread
MAX_SPREAD_BPS_EXEC = 3.0
TAKER_FEE_BPS_SIM = 6.0 # ~6 bps taker fee in PAPER sim

def _book_mid_spread(ob: Dict[str, Any]) -> tuple[float, float, float]:
    best_bid = float(ob["bids"][0][0]) if ob["bids"] else float("nan")
    best_ask = float(ob["asks"][0][0]) if ob["asks"] else float("nan")
    if not (best_bid > 0 and best_ask > 0 and best_ask > best_bid):
        return float("nan"), float("nan"), float("inf")
    mid = (best_bid + best_ask) / 2.0
    spr = (best_ask - best_bid)
    spr_bps = spr / mid * 1e4
    return mid, spr, spr_bps

def _post_only_price(side: str, mid: float, spr: float) -> float:
    return max(0.0, mid - POST_ONLY_K * spr) if side == "buy" else (mid + POST_ONLY_K * spr)

class ExecutionAgent(BaseAgent):
    def __init__(self, exchange: Exchange, pricefeed: PriceFeed, bus: SignalBus, **kwargs):
        super().__init__(**kwargs)
        self.exchange = exchange
        self.pricefeed = pricefeed
        self.bus = bus
        self._sub = None

    async def start(self):
        await super().start()
        # subscribe to the bus
        self._sub = await self.bus.subscribe()

    async def stop(self):
        if self._sub:
            try:
                await self.bus.unsubscribe(self._sub)
            except Exception:
                pass
        await super().stop()

    async def _execute_post_only(self, symbol: str, side: str, qty: float) -> Dict[str, Any]:
        ob = await self.pricefeed.get_orderbook(symbol)
        mid, spr, spr_bps = _book_mid_spread(ob)
        if spr_bps > MAX_SPREAD_BPS_EXEC:
            log.info(f"[exec] skip {symbol}: wide spread {spr_bps:.2f}bps")
            return {"filled": 0.0, "avg_px": None, "fees": 0.0, "maker": True}

        limit_px = _post_only_price(side, mid, spr)
        live = is_live()

        if live:
            # Kraken via ccxt – postOnly supported via params. Adjust to your Kraken wrapper if needed.
            order = await self.exchange.create_order(
                symbol, type="limit", side=side, amount=qty, price=limit_px, params={"postOnly": True}
            )
            order_id = order["id"]
            last_mid = mid
            start_ts = time.time()
            while True:
                status = await self.exchange.fetch_order(order_id, symbol)
                filled = float(status.get("filled", 0.0))
                remaining = float(status.get("remaining", 0.0))

                # refresh book and check adverse move
                ob = await self.exchange.fetch_order_book(symbol, limit=5)
                mid, spr, spr_bps = _book_mid_spread(ob)
                adverse_move = abs(mid - last_mid)
                last_mid = mid

                if filled > 0.0 and remaining <= 1e-12:
                    avg_px = float(status.get("average", limit_px))
                    return {"filled": filled, "avg_px": avg_px, "fees": 0.0, "maker": True}

                if (time.time() - start_ts) > REPRICE_SECS or adverse_move > (REPRICE_MOVE * spr):
                    try:
                        await self.exchange.cancel_order(order_id, symbol)
                    except Exception:
                        pass
                    limit_px = _post_only_price(side, mid, spr)
                    order = await self.exchange.create_order(
                        symbol, type="limit", side=side, amount=remaining if remaining > 0 else qty,
                        price=limit_px, params={"postOnly": True}
                    )
                    order_id = order["id"]
                    start_ts = time.time()
                await asyncio.sleep(0.5)
        else:
            # PAPER: maker-first model, degrade to taker if price runs away.
            maker_fill = False
            simulated_mid_move = 0.25 * spr
            exec_price = (mid - 0.1 * spr - simulated_mid_move) if side == "buy" else (mid + 0.1 * spr + simulated_mid_move)
            if (side == "buy" and exec_price <= limit_px) or (side == "sell" and exec_price >= limit_px):
                maker_fill = True
                px = limit_px
                fees = 0.0
            else:
                # taker penalty: 1/2 spread + fee bps
                penalty = 0.5 * spr
                px = (exec_price + penalty) if side == "buy" else (exec_price - penalty)
                notional = abs(px * qty)
                fees = (TAKER_FEE_BPS_SIM / 1e4) * notional

            return {"filled": qty, "avg_px": float(px), "fees": float(fees), "maker": maker_fill}

    async def run(self):
        max_pos = float(settings.MAX_POSITION)
        long_only = bool(settings.LONG_ONLY)
        order_size = float(settings.ORDER_SIZE)

        # naive per-symbol position book (PnL engine elsewhere)
        positions: dict[str, float] = {s: 0.0 for s in self.symbols}

        while self._running.is_set():
            sig: Signal = await self._sub.get()  # type: ignore[assignment]
            if sig.symbol not in self.symbols:
                continue

            side = sig.side.lower()
            qty = float(sig.qty or order_size)

            # long-only guard
            if long_only and side == "sell" and positions[sig.symbol] <= 0:
                log.debug("[exec] LONG_ONLY: ignore sell while flat")
                continue

            # position cap
            if side == "buy" and positions[sig.symbol] + qty > max_pos:
                qty = max(0.0, max_pos - positions[sig.symbol])
                if qty <= 0:
                    log.info(f"[exec] skip buy {sig.symbol}: position cap reached")
                    continue

            fill = await self._execute_post_only(sig.symbol, side, qty)
            if fill["filled"] <= 0:
                continue

            delta = qty if side == "buy" else -qty
            positions[sig.symbol] += delta

            log.info(
                f"[exec] {side} {sig.symbol} filled={fill['filled']} avg_px={fill['avg_px']} "
                f"maker={fill['maker']} fees={fill['fees']:.2f} | reason={sig.reason}"
            )
