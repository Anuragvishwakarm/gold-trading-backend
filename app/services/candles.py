"""Candle bucketing helpers shared by the repository and the live stream.

All bars are aligned to Indian Standard Time (MCX trades in IST):

* intraday bars (1m … 1h) align to the clock,
* 4h bars align to the 09:00 session open (09:00, 13:00, 17:00, 21:00),
* daily bars start at 00:00 IST, weekly bars on Monday, monthly bars on the 1st.

The Python ``bucket_start`` and the MongoDB ``mongo_bucket_expression`` must
always produce identical bucket keys; the tests check this.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from app.core.intervals import Timeframe


MARKET_TIMEZONE_NAME = "Asia/Kolkata"
IST = timezone(timedelta(hours=5, minutes=30), name="IST")


def bucket_start(moment: datetime, timeframe: Timeframe) -> datetime:
    """Return the UTC start of the bar that contains ``moment``."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    offset = timedelta(minutes=timeframe.anchor_offset_minutes)
    local = moment.astimezone(IST) - offset
    size = timeframe.bin_size

    if timeframe.unit == "minute":
        floored = local.replace(
            minute=local.minute - local.minute % size, second=0, microsecond=0
        )
    elif timeframe.unit == "hour":
        floored = local.replace(
            hour=local.hour - local.hour % size, minute=0, second=0, microsecond=0
        )
    elif timeframe.unit == "day":
        floored = local.replace(hour=0, minute=0, second=0, microsecond=0)
    elif timeframe.unit == "week":
        day = local.replace(hour=0, minute=0, second=0, microsecond=0)
        floored = day - timedelta(days=day.weekday())
    elif timeframe.unit == "month":
        floored = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:  # pragma: no cover - guarded by TIMEFRAMES
        raise ValueError(f"Unsupported timeframe unit: {timeframe.unit}")

    return (floored + offset).astimezone(timezone.utc)


def mongo_bucket_expression(timeframe: Timeframe, field: str = "$minute") -> dict[str, Any]:
    """MongoDB expression equivalent to :func:`bucket_start`."""
    offset = timeframe.anchor_offset_minutes
    date: Any = field
    if offset:
        date = {"$dateSubtract": {"startDate": field, "unit": "minute", "amount": offset}}

    trunc: dict[str, Any] = {
        "date": date,
        "unit": timeframe.unit,
        "binSize": timeframe.bin_size,
        "timezone": MARKET_TIMEZONE_NAME,
    }
    if timeframe.unit == "week":
        trunc["startOfWeek"] = "monday"
    expression: dict[str, Any] = {"$dateTrunc": trunc}

    if offset:
        expression = {
            "$dateAdd": {"startDate": expression, "unit": "minute", "amount": offset}
        }
    return expression


def aggregate_candles(
    candles: Iterable[dict[str, Any]],
    timeframe: Timeframe,
    symbol: str = "GOLD",
) -> list[dict[str, Any]]:
    """Group ascending candles into ``timeframe`` bars in Python."""
    buckets: dict[datetime, dict[str, Any]] = {}
    for candle in candles:
        key = bucket_start(candle["minute"], timeframe)
        bar = buckets.get(key)
        if bar is None:
            buckets[key] = {
                "instrument_key": candle["instrument_key"],
                "trading_symbol": candle.get("trading_symbol"),
                "underlying_symbol": candle.get("underlying_symbol") or symbol,
                "interval": timeframe.key,
                "minute": key,
                "open": candle["open"],
                "high": candle["high"],
                "low": candle["low"],
                "close": candle["close"],
                "volume": candle.get("volume") or 0,
                "cumulative_volume": candle.get("cumulative_volume"),
                "open_interest": candle.get("open_interest"),
                "tick_count": candle.get("tick_count") or 0,
                "updated_at": candle.get("updated_at") or key,
            }
            continue
        bar["high"] = max(bar["high"], candle["high"])
        bar["low"] = min(bar["low"], candle["low"])
        bar["close"] = candle["close"]
        bar["volume"] += candle.get("volume") or 0
        bar["tick_count"] += candle.get("tick_count") or 0
        bar["instrument_key"] = candle["instrument_key"]
        bar["trading_symbol"] = candle.get("trading_symbol") or bar["trading_symbol"]
        if candle.get("cumulative_volume") is not None:
            bar["cumulative_volume"] = candle["cumulative_volume"]
        if candle.get("open_interest") is not None:
            bar["open_interest"] = candle["open_interest"]
        if candle.get("updated_at") and candle["updated_at"] > bar["updated_at"]:
            bar["updated_at"] = candle["updated_at"]

    result = [buckets[key] for key in sorted(buckets)]
    for bar in result:
        bar["id"] = f"{bar['instrument_key']}:{timeframe.key}:{bar['minute'].isoformat()}"
    return result
