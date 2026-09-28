from __future__ import annotations

from typing import Any

from app.core.intervals import TIMEFRAMES
from app.services.technical_indicators import (
    MINIMUM_CANDLES,
    calculate_technical_indicators,
)


INTERVAL_MINUTES: dict[str, int] = {
    key: timeframe.approx_minutes for key, timeframe in TIMEFRAMES.items()
}
INDICATOR_LOOKBACK = 500


def _round(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(value, digits)


def horizon_in_candles(interval: str, horizon_minutes: int) -> int:
    interval_minutes = INTERVAL_MINUTES[interval]
    if horizon_minutes < interval_minutes:
        raise ValueError(
            f"horizon must be at least {interval_minutes} minutes for {interval} candles"
        )
    if horizon_minutes % interval_minutes != 0:
        raise ValueError(
            f"horizon must be divisible by {interval_minutes} for {interval} candles"
        )
    return horizon_minutes // interval_minutes


def _direction_summary(
    signal: str, results: list[dict[str, Any]]
) -> dict[str, Any]:
    selected = [item for item in results if item["signal"] == signal]
    wins = sum(item["result"] == "win" for item in selected)
    losses = sum(item["result"] == "loss" for item in selected)
    pending = sum(item["result"] == "pending" for item in selected)
    evaluated = wins + losses
    return {
        "signal": signal,
        "total": len(selected),
        "evaluated": evaluated,
        "wins": wins,
        "losses": losses,
        "pending": pending,
        "win_rate": _round((wins / evaluated) * 100, 2) if evaluated else None,
    }


def calculate_backtest(
    candles: list[dict[str, Any]],
    interval: str,
    horizon_minutes: int,
    minimum_move_percent: float = 0.0,
    recent_limit: int = 50,
) -> dict[str, Any]:
    if not candles:
        raise ValueError("At least one candle is required")

    ordered = sorted(candles, key=lambda candle: candle["minute"])
    horizon_candles = horizon_in_candles(interval, horizon_minutes)
    results: list[dict[str, Any]] = []
    neutral_snapshots = 0
    signal_snapshots = 0

    for index in range(MINIMUM_CANDLES - 1, len(ordered)):
        window_start = max(0, index - INDICATOR_LOOKBACK + 1)
        snapshot = calculate_technical_indicators(
            ordered[window_start : index + 1], interval
        )
        signal_snapshots += 1
        signal = snapshot["signal"]
        if signal not in {"buy", "sell"}:
            neutral_snapshots += 1
            continue

        entry = ordered[index]
        entry_price = float(entry["close"])
        evaluation_index = index + horizon_candles
        result: dict[str, Any] = {
            "signal_time": entry["minute"],
            "evaluation_time": None,
            "signal": signal,
            "result": "pending",
            "entry_price": round(entry_price, 2),
            "exit_price": None,
            "price_change": None,
            "price_change_percent": None,
            "directional_return_percent": None,
            "reasons": snapshot["reasons"],
        }

        if evaluation_index < len(ordered):
            evaluation = ordered[evaluation_index]
            exit_price = float(evaluation["close"])
            price_change = exit_price - entry_price
            price_change_percent = (
                (price_change / entry_price) * 100 if entry_price else 0.0
            )
            directional_return = (
                price_change_percent if signal == "buy" else -price_change_percent
            )
            result.update(
                {
                    "evaluation_time": evaluation["minute"],
                    "result": (
                        "win"
                        if directional_return > minimum_move_percent
                        else "loss"
                    ),
                    "exit_price": round(exit_price, 2),
                    "price_change": _round(price_change, 2),
                    "price_change_percent": _round(price_change_percent, 4),
                    "directional_return_percent": _round(directional_return, 4),
                }
            )
        results.append(result)

    wins = sum(item["result"] == "win" for item in results)
    losses = sum(item["result"] == "loss" for item in results)
    pending = sum(item["result"] == "pending" for item in results)
    evaluated = wins + losses
    directional_returns = [
        float(item["directional_return_percent"])
        for item in results
        if item["directional_return_percent"] is not None
    ]
    latest = ordered[-1]

    return {
        "instrument_key": latest["instrument_key"],
        "trading_symbol": latest.get("trading_symbol"),
        "interval": interval,
        "horizon_minutes": horizon_minutes,
        "horizon_candles": horizon_candles,
        "minimum_move_percent": round(minimum_move_percent, 4),
        "analysis_start": ordered[0]["minute"],
        "analysis_end": latest["minute"],
        "candles_analyzed": len(ordered),
        "signal_snapshots": signal_snapshots,
        "neutral_snapshots": neutral_snapshots,
        "total_signals": len(results),
        "evaluated_signals": evaluated,
        "winning_signals": wins,
        "losing_signals": losses,
        "pending_signals": pending,
        "win_rate": _round((wins / evaluated) * 100, 2) if evaluated else None,
        "average_directional_return_percent": (
            _round(sum(directional_returns) / len(directional_returns), 4)
            if directional_returns
            else None
        ),
        "buy": _direction_summary("buy", results),
        "sell": _direction_summary("sell", results),
        "recent_results": list(reversed(results[-recent_limit:])),
    }
