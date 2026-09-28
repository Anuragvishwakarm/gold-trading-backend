from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class APIModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class InstrumentResponse(APIModel):
    id: str
    instrument_key: str
    trading_symbol: str | None = None
    underlying_symbol: str | None = None
    name: str | None = None
    segment: str
    instrument_type: str
    expiry: datetime | int | None = None
    lot_size: int | None = None
    tick_size: float | None = None


class TickResponse(APIModel):
    id: str
    instrument_key: str
    trading_symbol: str | None = None
    underlying_symbol: str | None = None
    received_at: datetime
    feed_timestamp: datetime | None = None
    last_traded_at: datetime | None = None
    ltp: float
    close_price: float | None = None
    last_traded_quantity: int | None = None
    average_traded_price: float | None = None
    volume_traded_today: int | None = None
    open_interest: int | None = None
    total_buy_quantity: int | None = None
    total_sell_quantity: int | None = None
    best_bid_price: float | None = None
    best_bid_quantity: int | None = None
    best_ask_price: float | None = None
    best_ask_quantity: int | None = None


class CandleResponse(APIModel):
    id: str
    instrument_key: str
    trading_symbol: str | None = None
    underlying_symbol: str = "GOLD"
    interval: str = "1m"
    minute: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int | None = None
    cumulative_volume: int | None = None
    open_interest: int | None = None
    tick_count: int
    updated_at: datetime
