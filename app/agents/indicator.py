# app/agents/indicator.py
from __future__ import annotations
import asyncio, math, time, logging
from typing import Any, Dict, List
import numpy as np

from .base import BaseAgent
from ..core.signals import Signal, SignalBus
from ..core.config import settings
from ..services.pricefeed import PriceFeed

log = logging.getLogger("agent.indicator")

RSI_LEN = 14
ATR_LEN = 14
EMA_FAST = 12
EMA_SLOW = 26
EMA_SIG  = 9
EMA_TREND = 200
EMA_TREND_SLOPE_BARS = 5

MAX_SPREAD_BPS = 8.0          # relaxed a bit so we at least see activity
MIN_ATR_PCT   = 0.0015        # 0.15% floor for debug
MIN_BID_IMB   = 0.52

RSI_MOMENTUM_MIN = 60.0
RSI_MEANREV_MAX  = 30.0

MIN_BARS_FOR_COMPUTE = 210
INTERVAL_SEC = 2.0

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

def _mid(b: float, a: float) -> float: return (b + a) / 2.0
def _spr_bps(b: float, a: float) -> float:
    m = _mid(b, a); 
    return float("inf") if m <= 0 else (a - b) / m * 1e4

def _imb(bv: float, av: float) -> float:
    d = bv + av
    return 0.5 if d <= 0 else bv / d

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
                    ob = await self.pricefeed.get_orderbook(sym)
                    best_bid = ob["bids"][0][0] if ob["bids"] else math.nan
                    best_ask = ob["asks"][0][0] if ob["asks"] else math.nan
                    bidv    = ob["bids"][0][1] if ob["bids"] else 0.0
                    askv    = ob["asks"][0][1] if ob["asks"] else 0.0

                    candles = await self.pricefeed.get_recent_klines(sym, limit=300)
                    closes = np.array([c["close"] for c in candles], dtype=float)
                    highs  = np.maximum(closes, closes * 1.001)
                    lows   = np.minimum(closes,  closes * 0.999)

                    if len(closes) < MIN_BARS_FOR_COMPUTE:
                        log.debug("[indicator] %s skip: bars=%d (<%d)", sym, len(closes), MIN_BARS_FOR_COMPUTE)
                        continue
                    if not (best_bid > 0 and best_ask > 0 and best_ask > best_bid):
                        log.debug("[indicator] %s skip: invalid book (bid=%s ask=%s)", sym, best_bid, best_ask)
                        continue

                    rsi_v = _rsi(closes)
                    macd_line, macd_sig, macd_hist = _macd(closes)
                    atr_v = _atr(highs, lows, closes)
                    spr_bps = _spr_bps(best_bid, best_ask)
                    imb = _imb(bidv, askv)
                    mid = _mid(best_bid, best_ask)

                    if spr_bps > MAX_SPREAD_BPS:
                        log.debug("[indicator] %s gate: spread %.2fbps>%0.2f", sym, spr_bps, MAX_SPREAD_BPS)
                        continue
                    if not (atr_v > 0 and (atr_v / mid) >= MIN_ATR_PCT):
                        log.debug("[indicator] %s gate: ATR%% %.5f<%.5f", sym, (atr_v / mid) if mid>0 else -1, MIN_ATR_PCT)
                        continue

                    trend = (macd_hist > 0.0) and (closes[-1] > np.mean(closes[-200:]))
                    mode = "MOMENTUM" if trend else "MEAN_REVERT"

                    should_buy = False
                    reason = ""
                    if mode == "MOMENTUM":
                        if rsi_v >= RSI_MOMENTUM_MIN and imb >= MIN_BID_IMB:
                            should_buy = True
                            reason = f"RSI_breakout({rsi_v:.1f}) hist={macd_hist:.4f} imb={imb:.2f}"
                    else:
                        if rsi_v <= RSI_MEANREV_MAX:
                            should_buy = True
                            reason = f"RSI_oversold({rsi_v:.1f}) atr%={(atr_v/mid):.4f}"

                    log.debug("[indicator] %s %s rsi=%.1f hist=%.5f atr%%=%.4f spr=%.2fbps imb=%.2f",
                              sym, mode, rsi_v, macd_hist, (atr_v/mid), spr_bps, imb)

                    if should_buy and settings.LONG_ONLY:
                        await self.bus.publish(Signal(symbol=sym, side="buy", qty=qty, reason=reason, ts=time.time()))
                        log.info(f"[indicator] buy {sym} | {reason}")

                except Exception:
                    log.exception("indicator error for %s", sym)

            await asyncio.sleep(interval)
