# app/core/config.py
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import List, Optional
import json
import re

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- Modes & runtime ---
    MODE: str = Field(default="paper")  # "paper" or "live"
    LIVE: bool = Field(default=False)   # convenience flag used by some logs

    # --- Symbols & sizing ---
    ALLOWED_SYMBOLS: List[str] = Field(default_factory=lambda: ["BTC/CAD", "ETH/CAD"])
    MAX_POSITION: float = 50.0
    ORDER_SIZE: float = 10.0
    PER_TRADE_RISK_PCT: float = 0.01
    MAX_DAILY_LOSS: float = 100.0
    LONG_ONLY: bool = True

    # --- Market data feed ---
    FEED_MODE: str = "rest"  # "rest" | "ws"

    # --- Exchange creds (live only) ---
    KRAKEN_API_KEY: Optional[str] = None
    KRAKEN_API_SECRET: Optional[str] = None

    # --- Logging ---
    LOG_LEVEL: str = "INFO"

    # ---- Validators ----
    @field_validator("MODE")
    @classmethod
    def valid_mode(cls, v: str) -> str:
        v2 = v.lower().strip()
        if v2 not in ("paper", "live"):
            raise ValueError("MODE must be 'paper' or 'live'")
        return v2

    @field_validator("FEED_MODE")
    @classmethod
    def feed_mode_ok(cls, v: str) -> str:
        v2 = v.lower().strip()
        if v2 not in ("rest", "ws"):
            raise ValueError("FEED_MODE must be 'rest' or 'ws'")
        return v2

    @field_validator("ALLOWED_SYMBOLS", mode="before")
    @classmethod
    def parse_symbols(cls, v):
        """
        Accept JSON array (e.g. '["BTC/CAD","ETH/CAD"]') OR CSV (e.g. 'BTC/CAD,ETH/CAD').
        Also robust to stray brackets/quotes/whitespace.
        """
        # Already a list/tuple
        if isinstance(v, (list, tuple)):
            return [str(x).strip() for x in v if str(x).strip()]

        if v is None:
            return ["BTC/CAD", "ETH/CAD"]

        s = str(v).strip()
        if not s:
            return ["BTC/CAD", "ETH/CAD"]

        # Try JSON first
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except Exception:
            pass

        # Fallback: CSV / whitespace, stripping common wrappers
        s = s.strip(" []\"'")
        tokens = [t.strip() for t in re.split(r"[,\s]+", s) if t.strip()]
        return tokens or ["BTC/CAD", "ETH/CAD"]

settings = Settings()

def is_live() -> bool:
    # Keep both interpretations in sync; either MODE=live or LIVE=true will be treated as live,
    # but we also require API creds to be present for actual live trading codepaths.
    return (settings.MODE == "live" or bool(settings.LIVE)) and bool(settings.KRAKEN_API_KEY and settings.KRAKEN_API_SECRET)
