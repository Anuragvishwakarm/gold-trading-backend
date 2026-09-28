from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


from app.core.intervals import StoredIntervalName

# Only the two base series are stored; every chart timeframe is derived.
CandleIntervalName = StoredIntervalName


class HistoricalSyncRequest(BaseModel):
    intervals: list[CandleIntervalName] = Field(
        default_factory=lambda: ["1m", "1d"],
        min_length=1,
    )
    from_date: date | None = None
    to_date: date | None = None
    # Contract to sync; default = nearest expiry.
    instrument_key: str | None = None

    @model_validator(mode="after")
    def validate_date_range(self) -> "HistoricalSyncRequest":
        if self.from_date and self.to_date and self.from_date > self.to_date:
            raise ValueError("from_date must be on or before to_date")
        self.intervals = list(dict.fromkeys(self.intervals))
        return self


class IntervalSyncResult(BaseModel):
    # ``str`` so older sync logs (5m/15m/1h) still load.
    interval: str
    fetched: int
    upserted: int
    modified: int
    requests: int


class HistoricalSyncResponse(BaseModel):
    sync_id: str
    status: Literal["completed", "failed"]
    instrument_key: str
    trading_symbol: str | None = None
    from_date: date
    to_date: date
    started_at: datetime
    finished_at: datetime
    results: list[IntervalSyncResult]


class HistoricalSyncStatus(BaseModel):
    sync_id: str
    status: str
    instrument_key: str
    trading_symbol: str | None = None
    from_date: date
    to_date: date
    intervals: list[str]
    started_at: datetime
    finished_at: datetime | None = None
    results: list[IntervalSyncResult] = Field(default_factory=list)
    error: str | None = None


class DataQualityResponse(BaseModel):
    interval: CandleIntervalName
    collection: str
    total_candles: int
    first_candle_at: datetime | None = None
    last_candle_at: datetime | None = None
    duplicate_groups: int
    invalid_ohlc: int
    non_positive_prices: int
    missing_or_invalid_volume: int
    status: Literal["ok", "issues_found", "no_data"]
