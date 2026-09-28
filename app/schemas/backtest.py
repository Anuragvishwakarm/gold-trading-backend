from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.analytics import AnalyticsInterval


BacktestSignal = Literal["buy", "sell"]
BacktestResult = Literal["win", "loss", "pending"]


class DirectionSummary(BaseModel):
    signal: BacktestSignal
    total: int
    evaluated: int
    wins: int
    losses: int
    pending: int
    win_rate: float | None = None


class BacktestSignalResult(BaseModel):
    signal_time: datetime
    evaluation_time: datetime | None = None
    signal: BacktestSignal
    result: BacktestResult
    entry_price: float
    exit_price: float | None = None
    price_change: float | None = None
    price_change_percent: float | None = None
    directional_return_percent: float | None = None
    reasons: list[str]


class BacktestSummaryResponse(BaseModel):
    instrument_key: str
    trading_symbol: str | None = None
    interval: AnalyticsInterval
    horizon_minutes: int
    horizon_candles: int
    minimum_move_percent: float
    analysis_start: datetime
    analysis_end: datetime
    candles_analyzed: int
    signal_snapshots: int
    neutral_snapshots: int
    total_signals: int
    evaluated_signals: int
    winning_signals: int
    losing_signals: int
    pending_signals: int
    win_rate: float | None = None
    average_directional_return_percent: float | None = None
    buy: DirectionSummary
    sell: DirectionSummary
    recent_results: list[BacktestSignalResult]
