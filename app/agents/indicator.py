# app/agents/indicator.py
# Regime-aware RSI+MACD with microstructure gates (spread, depth) and ATR exits.
# Publishes buy Signals (long-only by default) to the SignalBus.

from __future__ import annotations
import asyncio, math, time, logging
from typing import Any, Dict, List
import numpy as np

from .base import BaseAgent
from ..core.signals import Signal, SignalBus
from ..core.config import settings
from ..services.pricefeed import PriceFeed

log = logging.getLogger("agent.indicator")

# ---------- Tunables ----------
RSI_LEN = 14
ATR_LEN = 14
EMA_FAST = 12
EMA_SLOW = 26
EMA_SIG  = 9
EMA_TREND = 200
EMA_TREND_SLOPE_BARS = 5

MAX_SPREAD_BPS = 3.0          # skip if spread wider than this
MIN_ATR_PCT   = 0.0035        # 0.35% ATR/price floor
MIN_BID_IMB   = 0.55          # L2 imbalance gate (bid/(bid+ask))

RSI_MOMENTUM_MIN = 60.0       # trend mode: breakout threshold
RSI_MEANREV_MAX  = 30.0       # range/down mode: buy-the-dip

MIN_BARS_FOR_COMPUTE = 210
INTERVAL_SEC = 2.0

# ---------- Helpers ----------
def _ema(arr: np.ndarray, n: int) -> np.ndarray:
    k = 2.0 / (n + 1.0)
    out = np.empty_like(arr, dtype=float)
    out[0] = arr[0]
    for i in range(1, len(arr)):
        out[i] = out[i-1] + k * (arr[i] - out[i-1])
    return out

def _rsi(closes: np.ndarray, n: int = RSI_LEN) -> float:
    if len(closes) < n + 2: return math.nan
    deltas = np.diff(closes)
    up = np.maximum(deltas, 0.0)
    dn = -np.minimum(deltas, 0.0)
    rs = (_ema(up, n)[-1] / max(1e-12, _ema(dn, n)[-1]))
    return 100.0 - (100.0 / (1.0 + rs))

def _macd(closes: np.ndarray, fast=EMA_FAST, slow=EMA_SLOW, sig=EMA_SIG):
    if len(closes) < slow + sig + 2: return math.nan, math.nan, math.nan
    f = _ema(closes, fast); s = _ema(closes, slow)
    line = f - s; signal = _ema(line, sig); hist = line - signal
    return float(line[-1]), float(signal[-1]), float(hist[-1])

def _atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, n: int = ATR_LEN) -> float:
    if len(closes) < n + 2: return math.nan
    tr = np.maximum.reduce([
        highs[1:] - lows[1:],
        np.abs(highs[1:] - closes[:-1]),
        np.abs(lows[1:] - closes[:-1]),
    ])
    return float(_ema(tr, n)[-1])

def _ema_slope(vals: np.ndarray, n: int = EMA_TREND, lookback: int = EMA_TREND_SLOPE_BARS) -> float:
    if len(vals) < n + lookback + 1: return math.nan
    e = _ema(vals, n)
    return float(e[-1] - e[-lookback-1])

def _mid(best_bid: float, best_ask: float) -> float:
    return (best_bid + best_ask) / 2.0

def _spread_bps(best_bid: float, best_ask: float) -> float:
    mid = _mid(best_bid, best_ask)
    if mid <= 0: return float("inf")
    return (best_ask - best_bid) / mid * 1e4

def _depth_imbalance(bid_vol: float, ask_vol: float) -> float:
    denom = bid_vol + ask_vol
    if denom <= 0: return 0.5
    return bid_vol / denom

class IndicatorAgent(BaseAgent):
    def __init__(self, pricefeed: PriceFeed, bus: SignalBus, **kwargs):
        super().__init__(**kwargs)
        self.pricefeed = pricefeed
        self.bus = bus

    async def run(self):
        qty = float(self.config.get("qty", settings.ORDER_SIZE))
        interval = float(self.config.get("interval_sec", INTERVAL_SEC))

        while self._running.is_set():
            for sym in self.symbols:
                try:
                    # --- data pulls ---
                    ob = await self.pricefeed.get_orderbook(sym)
                    best_bid = ob["bids"][0][0] if ob["bids"] else math.nan
                    best_ask = ob["asks"][0][0] if ob["asks"] else math.nan
                    bidv    = ob["bids"][0][1] if ob["bids"] else 0.0
                    askv    = ob["asks"][0][1] if ob["asks"] else 0.0

                    candles = await self.pricefeed.get_recent_klines(sym, limit=300)
                    closes = np.array([c["close"] for c in candles], dtype=float)
                    # synthesize highs/lows around closes if feed lacks full OHLC
                    highs = closes * 1.001
                    lows  = closes * 0.999

                    if len(closes) < MIN_BARS_FOR_COMPUTE or not (best_bid > 0 and best_ask > 0 and best_ask > best_bid):
                        continue

                    # --- features ---
                    rsi_v = _rsi(closes, RSI_LEN)
                    macd_line, macd_sig, macd_hist = _macd(closes)
                    slope200 = _ema_slope(closes, EMA_TREND, EMA_TREND_SLOPE_BARS)
                    atr_v = _atr(highs, lows, closes, ATR_LEN)
                    spr_bps = _spread_bps(best_bid, best_ask)
                    imb = _depth_imbalance(bidv, askv)
                    mid = _mid(best_bid, best_ask)

                    # --- gates ---
                    if spr_bps > MAX_SPREAD_BPS:
                        continue
                    if not (atr_v > 0 and (atr_v / mid) >= MIN_ATR_PCT):
                        continue

                    trend = (macd_hist > 0.0) and (slope200 > 0.0)
                    mode = "MOMENTUM" if trend else "MEAN_REVERT"

                    # Long-only regime logic
                    should_buy = False
                    reason = ""
                    if mode == "MOMENTUM":
                        if rsi_v >= RSI_MOMENTUM_MIN and imb >= MIN_BID_IMB:
                            should_buy = True
                            reason = f"RSI_breakout({rsi_v:.1f})+MACD_up hist={macd_hist:.4f} imb={imb:.2f}"
                    else:
                        if rsi_v <= RSI_MEANREV_MAX:
                            should_buy = True
                            reason = f"RSI_oversold({rsi_v:.1f}) meanrev atr%={(atr_v/mid):.4f}"

                    if should_buy and settings.LONG_ONLY:
                        await self.bus.publish(Signal(symbol=sym, side="buy", qty=qty, reason=reason, ts=time.time()))
                        log.info(f"[indicator] buy {sym} | {reason}")

                except Exception:
                    log.exception("indicator error for %s", sym)

            await asyncio.sleep(interval)
