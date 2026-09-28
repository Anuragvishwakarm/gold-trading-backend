from __future__ import annotations

from statistics import fmean, pstdev
from typing import Any


MINIMUM_CANDLES = 50


def _round(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(value, digits)


# ============================================================
# MOVING AVERAGES
# ============================================================

def sma_series(values: list[float], period: int) -> list[float | None]:
    """
    Calculate Simple Moving Average (SMA) for every data point.

    Example:
        values = [10, 20, 30]
        period = 2

        result = [None, 15, 25]

    The first period - 1 values are None because there is not
    enough historical data to calculate the moving average.
    """
    if period <= 0:
        raise ValueError("Moving average period must be greater than 0")

    if not values:
        return []

    result: list[float | None] = [None] * len(values)

    rolling_sum = 0.0

    for index, value in enumerate(values):
        rolling_sum += float(value)

        if index >= period:
            rolling_sum -= float(values[index - period])

        if index >= period - 1:
            result[index] = rolling_sum / period

    return result


def ema_series(values: list[float], period: int) -> list[float | None]:
    """
    Calculate Exponential Moving Average (EMA) for every data point.

    The first available value is used as the initial EMA value.
    """
    if period <= 0:
        raise ValueError("Moving average period must be greater than 0")

    if not values:
        return []

    multiplier = 2 / (period + 1)

    result: list[float | None] = [None] * len(values)

    previous_ema = float(values[0])
    result[0] = previous_ema

    for index, value in enumerate(values[1:], start=1):
        current_value = float(value)

        previous_ema = (
            (current_value - previous_ema) * multiplier
            + previous_ema
        )

        result[index] = previous_ema

    return result


def moving_average_series(
    values: list[float],
    period: int,
    ma_type: str = "sma",
) -> list[float | None]:
    """
    Generic Moving Average dispatcher.

    Supported:
        - SMA
        - EMA

    Future types such as WMA/VWMA/HMA can be added here.
    """
    normalized_type = ma_type.strip().lower()

    if normalized_type == "sma":
        return sma_series(values, period)

    if normalized_type == "ema":
        return ema_series(values, period)

    raise ValueError(
        f"Unsupported moving average type: {ma_type}. "
        "Supported types: SMA, EMA"
    )


# ============================================================
# RSI
# ============================================================

def rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None

    changes = [
        current - previous
        for previous, current in zip(values, values[1:])
    ]

    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]

    average_gain = fmean(gains[:period])
    average_loss = fmean(losses[:period])

    for gain, loss in zip(gains[period:], losses[period:]):
        average_gain = (
            ((average_gain * (period - 1)) + gain) / period
        )

        average_loss = (
            ((average_loss * (period - 1)) + loss) / period
        )

    if average_gain == 0 and average_loss == 0:
        return 50.0

    if average_loss == 0:
        return 100.0

    relative_strength = average_gain / average_loss

    return 100 - (100 / (1 + relative_strength))


# ============================================================
# ATR
# ============================================================

def atr(
    candles: list[dict[str, Any]],
    period: int = 14,
) -> float | None:
    if len(candles) < period:
        return None

    true_ranges: list[float] = []
    previous_close: float | None = None

    for candle in candles:
        high = float(candle["high"])
        low = float(candle["low"])

        if previous_close is None:
            true_range = high - low
        else:
            true_range = max(
                high - low,
                abs(high - previous_close),
                abs(low - previous_close),
            )

        true_ranges.append(true_range)
        previous_close = float(candle["close"])

    result = fmean(true_ranges[:period])

    for true_range in true_ranges[period:]:
        result = (
            ((result * (period - 1)) + true_range)
            / period
        )

    return result


# ============================================================
# HELPERS
# ============================================================

def percentage_change(
    current: int | float | None,
    previous: int | float | None,
) -> float | None:
    if (
        current is None
        or previous is None
        or float(previous) == 0
    ):
        return None

    return (
        (float(current) - float(previous))
        / abs(float(previous))
    ) * 100


# ============================================================
# COMPLETE TECHNICAL INDICATORS
# ============================================================

def calculate_technical_indicators(
    candles: list[dict[str, Any]],
    interval: str,
    ma_type: str = "sma",
    ma_period: int = 20,
) -> dict[str, Any]:

    if not candles:
        raise ValueError("At least one candle is required")

    closes = [
        float(candle["close"])
        for candle in candles
    ]

    # --------------------------------------------------------
    # Dynamic Moving Average
    # --------------------------------------------------------

    if ma_period <= 0:
        raise ValueError(
            "Moving average period must be greater than 0"
        )

    moving_average_values = moving_average_series(
        closes,
        ma_period,
        ma_type,
    )

    latest_moving_average = moving_average_values[-1]

    # --------------------------------------------------------
    # EMA
    # --------------------------------------------------------

    ema_9_series = ema_series(closes, 9)
    ema_21_series = ema_series(closes, 21)
    ema_50_series = ema_series(closes, 50)

    # MACD EMAs
    ema_12_series = ema_series(closes, 12)
    ema_26_series = ema_series(closes, 26)

    macd_series = [
        float(fast) - float(slow)
        for fast, slow in zip(
            ema_12_series,
            ema_26_series,
        )
        if fast is not None and slow is not None
    ]

    macd_signal_series = ema_series(
        macd_series,
        9,
    )

    # --------------------------------------------------------
    # Latest values
    # --------------------------------------------------------

    latest = candles[-1]

    close = closes[-1]

    ema_9 = ema_9_series[-1]
    ema_21 = ema_21_series[-1]
    ema_50 = ema_50_series[-1]

    macd_value = macd_series[-1]
    macd_signal = macd_signal_series[-1]

    rsi_value = rsi(closes)
    atr_value = atr(candles)

    # --------------------------------------------------------
    # Bollinger Bands
    # --------------------------------------------------------

    bollinger_middle: float | None = None
    bollinger_upper: float | None = None
    bollinger_lower: float | None = None

    if len(closes) >= 20:
        window = closes[-20:]

        bollinger_middle = fmean(window)

        deviation = pstdev(window)

        bollinger_upper = (
            bollinger_middle + (2 * deviation)
        )

        bollinger_lower = (
            bollinger_middle - (2 * deviation)
        )

    # --------------------------------------------------------
    # Trend
    # --------------------------------------------------------

    trend = "sideways"

    if (
        ema_9 is not None
        and ema_21 is not None
        and close > ema_21
        and ema_9 > ema_21
        and macd_value > macd_signal
    ):
        trend = "bullish"

    elif (
        ema_9 is not None
        and ema_21 is not None
        and close < ema_21
        and ema_9 < ema_21
        and macd_value < macd_signal
    ):
        trend = "bearish"

    # --------------------------------------------------------
    # Signal
    # --------------------------------------------------------

    sufficient_data = (
        len(candles) >= MINIMUM_CANDLES
    )

    signal = "neutral"

    reasons: list[str] = []

    if not sufficient_data:
        reasons.append(
            f"At least {MINIMUM_CANDLES} candles are required "
            "for a reliable signal"
        )

    else:
        if (
            ema_9 is not None
            and ema_21 is not None
            and ema_9 > ema_21
        ):
            reasons.append(
                "EMA 9 is above EMA 21"
            )

        elif (
            ema_9 is not None
            and ema_21 is not None
            and ema_9 < ema_21
        ):
            reasons.append(
                "EMA 9 is below EMA 21"
            )

        if macd_value > macd_signal:
            reasons.append(
                "MACD momentum is positive"
            )

        elif macd_value < macd_signal:
            reasons.append(
                "MACD momentum is negative"
            )

        if rsi_value is not None and rsi_value >= 70:
            reasons.append(
                "RSI is in the overbought zone"
            )

        elif rsi_value is not None and rsi_value <= 30:
            reasons.append(
                "RSI is in the oversold zone"
            )

        if (
            trend == "bullish"
            and rsi_value is not None
            and 45 <= rsi_value < 70
        ):
            signal = "buy"

        elif (
            trend == "bearish"
            and rsi_value is not None
            and 30 < rsi_value <= 55
        ):
            signal = "sell"

        else:
            reasons.append(
                "Indicator confirmation is mixed"
            )

    # --------------------------------------------------------
    # Volume
    # --------------------------------------------------------

    previous = (
        candles[-2]
        if len(candles) >= 2
        else {}
    )

    volume = latest.get("volume")

    if volume is None:
        volume = latest.get("cumulative_volume")

    previous_volume = previous.get("volume")

    if previous_volume is None:
        previous_volume = previous.get(
            "cumulative_volume"
        )

    # --------------------------------------------------------
    # Final response
    # --------------------------------------------------------
    return {
        "instrument_key": latest["instrument_key"],
        "trading_symbol": latest.get("trading_symbol"),
        "interval": interval,
        "candle_time": latest["minute"],
        "candles_used": len(candles),
        "minimum_candles": MINIMUM_CANDLES,
        "sufficient_data": sufficient_data,

        "close": _round(close, 2),

        "ema_9": _round(ema_9, 2),
        "ema_21": _round(ema_21, 2),
        "ema_50": _round(ema_50, 2),

        "moving_average": {
            "type": ma_type.lower(),
            "period": ma_period,
            "value": _round(latest_moving_average, 2),
        },

        "rsi_14": _round(rsi_value, 2),

        "macd": _round(macd_value, 4),
        "macd_signal": _round(macd_signal, 4),
        "macd_histogram": _round(
            macd_value - macd_signal,
            4,
        ),

        "bollinger_upper": _round(
            bollinger_upper,
            2,
        ),
        "bollinger_middle": _round(
            bollinger_middle,
            2,
        ),
        "bollinger_lower": _round(
            bollinger_lower,
            2,
        ),

        "atr_14": _round(
            atr_value,
            2,
        ),

        "volume_change_percent": _round(
            percentage_change(
                volume,
                previous_volume,
            ),
            2,
        ),

        "open_interest_change_percent": _round(
            percentage_change(
                latest.get("open_interest"),
                previous.get("open_interest"),
            ),
            2,
        ),

        "trend": trend,
        "signal": signal,
        "reasons": reasons,
    }