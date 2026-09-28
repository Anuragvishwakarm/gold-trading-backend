"""Candle interval definitions.

Two kinds of intervals exist in the system:

* **Stored intervals** are fetched from Upstox and persisted in MongoDB.
  Only two are needed: ``1m`` (intraday base) and ``1d`` (daily base).
* **Chart timeframes** are what the API serves to the frontend. They are
  always *derived* from a stored interval, so a single source of truth
  exists for every candle.

Timeframe keys use ``1mo`` for one month so it can never be confused with
``1m`` (one minute).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


# --------------------------------------------------------------------------
# Stored (Upstox) intervals
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CandleInterval:
    key: str
    unit: str  # Upstox V3 unit: minutes | hours | days
    value: int
    collection: str
    max_days_per_request: int


INTERVALS: dict[str, CandleInterval] = {
    "1m": CandleInterval("1m", "minutes", 1, "gold_candles_1m", 30),
    "1d": CandleInterval("1d", "days", 1, "gold_candles_1d", 365),
}

StoredIntervalName = Literal["1m", "1d"]


def get_interval(value: str) -> CandleInterval:
    try:
        return INTERVALS[value]
    except KeyError as exc:
        raise ValueError(f"Unsupported stored candle interval: {value}") from exc


# --------------------------------------------------------------------------
# Chart timeframes
# --------------------------------------------------------------------------

TimeframeName = Literal["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1mo"]


@dataclass(frozen=True)
class Timeframe:
    key: str
    # "minute" | "hour" | "day" | "week" | "month"
    unit: str
    bin_size: int
    # Stored interval the timeframe is built from.
    source: str
    # Shift applied before bucketing so bars line up with the MCX session
    # (09:00 IST). Only needed for multi-hour bars.
    anchor_offset_minutes: int = 0
    # Approximate length, used for backtest horizons.
    approx_minutes: int = 0


TIMEFRAMES: dict[str, Timeframe] = {
    "1m": Timeframe("1m", "minute", 1, "1m", approx_minutes=1),
    "5m": Timeframe("5m", "minute", 5, "1m", approx_minutes=5),
    "15m": Timeframe("15m", "minute", 15, "1m", approx_minutes=15),
    "30m": Timeframe("30m", "minute", 30, "1m", approx_minutes=30),
    "1h": Timeframe("1h", "hour", 1, "1m", approx_minutes=60),
    "4h": Timeframe("4h", "hour", 4, "1m", anchor_offset_minutes=9 * 60, approx_minutes=240),
    "1d": Timeframe("1d", "day", 1, "1d", approx_minutes=1440),
    "1w": Timeframe("1w", "week", 1, "1d", approx_minutes=10080),
    "1mo": Timeframe("1mo", "month", 1, "1d", approx_minutes=43200),
}


def get_timeframe(value: str) -> Timeframe:
    try:
        return TIMEFRAMES[value]
    except KeyError as exc:
        raise ValueError(f"Unsupported timeframe: {value}") from exc
