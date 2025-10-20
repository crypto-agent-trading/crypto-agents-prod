from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import List
import json

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    MODE: str = Field(default="paper")  # "paper" or "live"
    ALLOWED_SYMBOLS: List[str] = Field(default_factory=lambda: ["BTC/CAD", "ETH/CAD"])
    MAX_POSITION: float = 50.0
    ORDER_SIZE: float = 10.0
    PER_TRADE_RISK_PCT: float = 0.01
    MAX_DAILY_LOSS: float = 100.0
    FEED_MODE: str = "rest"  # rest | ws
    LONG_ONLY: bool = True

    KRAKEN_API_KEY: str | None = None
    KRAKEN_API_SECRET: str | None = None

    LOG_LEVEL: str = "INFO"

    @field_validator("MODE")
    @classmethod
    def valid_mode(cls, v: str) -> str:
        v2 = v.lower().strip()
        if v2 not in ("paper", "live"):
            raise ValueError("MODE must be 'paper' or 'live'")
        return v2

    @field_validator("ALLOWED_SYMBOLS", mode="before")
    @classmethod
    def parse_symbols(cls, v):
        # Accept JSON array or comma-separated string
        if isinstance(v, list):
            return v
        s = str(v).strip()
        if not s:
            return ["BTC/CAD", "ETH/CAD"]
        if s.startswith("["):
            try:
                arr = json.loads(s)
                if isinstance(arr, list):
                    return [str(x) for x in arr]
            except Exception:
                pass
        # fallback CSV
        return [x.strip() for x in s.split(",") if x.strip()]

    @field_validator("FEED_MODE")
    @classmethod
    def feed_mode_ok(cls, v: str) -> str:
        v2 = v.lower().strip()
        if v2 not in ("rest", "ws"):
            raise ValueError("FEED_MODE must be 'rest' or 'ws'")
        return v2

settings = Settings()

def is_live() -> bool:
    return settings.MODE == "live" and bool(settings.KRAKEN_API_KEY and settings.KRAKEN_API_SECRET)
