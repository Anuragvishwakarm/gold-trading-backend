from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _number(value: Any, cast: type = float) -> Any:
    if value in (None, ""):
        return None
    try:
        return cast(value)
    except (TypeError, ValueError):
        return None


def _datetime_from_ms(value: Any) -> datetime | None:
    number = _number(value, int)
    if number is None:
        return None
    try:
        return datetime.fromtimestamp(number / 1000, tz=timezone.utc)
    except (ValueError, OSError, OverflowError):
        return None


def _market_feed(feed: dict[str, Any]) -> dict[str, Any]:
    full_feed = feed.get("fullFeed") or feed.get("full_feed") or {}
    return (
        full_feed.get("marketFF")
        or full_feed.get("market_ff")
        or feed.get("marketFF")
        or feed.get("market_ff")
        or feed
    )


def normalize_message(
    message: Any,
    instrument_key: str,
    instrument: dict[str, Any],
    store_raw: bool,
) -> dict[str, Any] | None:
    if not isinstance(message, dict):
        return None

    feed = (message.get("feeds") or {}).get(instrument_key)
    if not isinstance(feed, dict):
        return None

    market = _market_feed(feed)
    ltpc = market.get("ltpc") or feed.get("ltpc") or {}
    ltp = _number(ltpc.get("ltp"))
    if ltp is None:
        return None

    received_at = datetime.now(timezone.utc)
    current_ts = message.get("currentTs") or message.get("current_ts")
    market_level = market.get("marketLevel") or market.get("market_level") or {}
    quotes = market_level.get("bidAskQuote") or market_level.get("bid_ask_quote") or []
    best_quote = quotes[0] if quotes else {}
    ohlc_container = market.get("marketOHLC") or market.get("market_ohlc") or {}

    document: dict[str, Any] = {
        "instrument_key": instrument_key,
        "trading_symbol": instrument.get("trading_symbol"),
        "underlying_symbol": instrument.get("underlying_symbol") or instrument.get("name"),
        "segment": instrument.get("segment"),
        "expiry": instrument.get("expiry"),
        "received_at": received_at,
        "feed_timestamp": _datetime_from_ms(current_ts),
        "last_traded_at": _datetime_from_ms(ltpc.get("ltt")),
        "ltp": ltp,
        "close_price": _number(ltpc.get("cp")),
        "last_traded_quantity": _number(ltpc.get("ltq"), int),
        "average_traded_price": _number(market.get("atp")),
        "volume_traded_today": _number(market.get("vtt"), int),
        "open_interest": _number(market.get("oi"), int),
        "total_buy_quantity": _number(market.get("tbq"), int),
        "total_sell_quantity": _number(market.get("tsq"), int),
        "best_bid_price": _number(best_quote.get("bidP") or best_quote.get("bid_p")),
        "best_bid_quantity": _number(best_quote.get("bidQ") or best_quote.get("bid_q"), int),
        "best_ask_price": _number(best_quote.get("askP") or best_quote.get("ask_p")),
        "best_ask_quantity": _number(best_quote.get("askQ") or best_quote.get("ask_q"), int),
        "upstox_ohlc": ohlc_container.get("ohlc") or [],
    }
    if store_raw:
        document["raw_message"] = message
    return document

