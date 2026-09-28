from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


from app.core.intervals import TimeframeName

AnalyticsInterval = TimeframeName

MovingAverageType = Literal["sma", "ema"]


class MovingAverageResponse(BaseModel):
    type: MovingAverageType
    period: int
    value: float | None = None


class AnalyticsResponse(BaseModel):
    instrument_key: str
    trading_symbol: str | None = None
    interval: AnalyticsInterval
    candle_time: datetime
    candles_used: int
    minimum_candles: int
    sufficient_data: bool

    close: float

    # Existing EMA indicators
    ema_9: float
    ema_21: float
    ema_50: float

    # Dynamic Moving Average
    moving_average: MovingAverageResponse

    # RSI
    rsi_14: float | None = None

    # MACD
    macd: float
    macd_signal: float
    macd_histogram: float

    # Bollinger Bands
    bollinger_upper: float | None = None
    bollinger_middle: float | None = None
    bollinger_lower: float | None = None

    # ATR
    atr_14: float | None = None

    # Market data changes
    volume_change_percent: float | None = None
    open_interest_change_percent: float | None = None

    # Trend / Signal
    trend: Literal["bullish", "bearish", "sideways"]
    signal: Literal["buy", "sell", "neutral"]
    reasons: list[str]