from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Gold Trading API"
    api_v1_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:3000"

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "trading_market_data"

    upstox_access_token: str = ""
    upstox_mode: str = "full"
    mcx_instruments_url: str = (
        "https://assets.upstox.com/market-quote/instruments/exchange/MCX.json.gz"
    )
    gold_underlying_symbol: str = "GOLD"
    # How many upcoming GOLD futures to collect (nearest first), e.g. Oct, Dec, Feb.
    gold_contract_count: int = 3
    store_raw_message: bool = True
    write_batch_size: int = 100
    write_flush_seconds: float = 1.0
    queue_max_size: int = 10_000
    auto_historical_backfill: bool = True
    # 1-minute history feeds 15m/30m/1h/4h charts; daily history feeds 1D/1W/1M.
    auto_backfill_days: int = 90
    auto_backfill_daily_days: int = 365
    auto_backfill_interval_hours: float = 6.0
    auto_backfill_retry_minutes: float = 15.0
    auto_backfill_start_delay_seconds: float = 5.0

    # Browser live stream (WebSocket /api/v1/market/stream)
    stream_poll_seconds: float = 1.0
    stream_heartbeat_seconds: float = 15.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @field_validator("upstox_mode")
    @classmethod
    def validate_mode(cls, value: str) -> str:
        value = value.lower().strip()
        if value not in {"ltpc", "full"}:
            raise ValueError("UPSTOX_MODE must be 'ltpc' or 'full'")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
