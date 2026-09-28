from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo import ASCENDING, DESCENDING

from app.core.intervals import TIMEFRAMES, get_interval, get_timeframe
from app.services.candles import aggregate_candles, bucket_start, mongo_bucket_expression


def _public_document(document: dict[str, Any] | None) -> dict[str, Any] | None:
    if document is None:
        return None
    result = dict(document)
    result["id"] = str(result.pop("_id"))
    result.pop("raw_message", None)
    return result


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class MarketRepository:
    """Read access to Gold instruments, ticks and candles.

    Candles for every chart timeframe are derived from two stored series:

    * ``gold_candles_1m`` for 1m, 5m, 15m, 30m, 1h and 4h bars;
    * ``gold_candles_1d`` (Upstox daily history) plus today's live 1m data
      for 1d, 1w and 1mo bars.
    """

    def __init__(self, database: Any) -> None:
        self.database = database

    # ------------------------------------------------------------------
    # Instrument and ticks
    # ------------------------------------------------------------------

    @staticmethod
    def _contract_filter(symbol: str) -> dict[str, Any]:
        # Keep contracts until a day after expiry so expiry-day charts still load.
        return {
            "$or": [{"underlying_symbol": symbol}, {"name": symbol}],
            "expiry": {"$gte": datetime.now(timezone.utc) - timedelta(days=1)},
        }

    async def list_instruments(self, symbol: str) -> list[dict[str, Any]]:
        """Collected, non-expired contracts, nearest expiry first."""
        cursor = self.database.instruments.find(self._contract_filter(symbol)).sort(
            "expiry", ASCENDING
        )
        documents = await cursor.to_list(length=20)
        return [item for item in (_public_document(doc) for doc in documents) if item]

    async def _find_active_instrument(
        self, symbol: str, instrument_key: str | None = None
    ) -> dict[str, Any] | None:
        """The requested contract, or the nearest-expiry one by default."""
        if instrument_key:
            return await self.database.instruments.find_one({"instrument_key": instrument_key})
        document = await self.database.instruments.find_one(
            self._contract_filter(symbol), sort=[("expiry", ASCENDING)]
        )
        if document is not None:
            return document
        # Older databases may lack expiry: fall back to the last saved contract.
        return await self.database.instruments.find_one(
            {"$or": [{"underlying_symbol": symbol}, {"name": symbol}]},
            sort=[("updated_at", DESCENDING)],
        )

    async def _tick_filter(self, symbol: str, instrument_key: str | None) -> dict[str, Any]:
        instrument = await self._find_active_instrument(symbol, instrument_key)
        query: dict[str, Any] = {"underlying_symbol": symbol}
        if instrument is not None:
            query["instrument_key"] = instrument["instrument_key"]
        elif instrument_key:
            query["instrument_key"] = instrument_key
        return query

    async def get_active_instrument(
        self, symbol: str, instrument_key: str | None = None
    ) -> dict[str, Any] | None:
        return _public_document(await self._find_active_instrument(symbol, instrument_key))

    async def get_latest_tick(
        self, symbol: str, instrument_key: str | None = None
    ) -> dict[str, Any] | None:
        document = await self.database.gold_ticks.find_one(
            await self._tick_filter(symbol, instrument_key),
            sort=[("received_at", DESCENDING)],
        )
        return _public_document(document)

    async def list_ticks(
        self, symbol: str, limit: int, instrument_key: str | None = None
    ) -> list[dict[str, Any]]:
        cursor = (
            self.database.gold_ticks.find(await self._tick_filter(symbol, instrument_key))
            .sort("received_at", DESCENDING)
            .limit(limit)
        )
        documents = await cursor.to_list(length=limit)
        return [_public_document(item) for item in documents if item is not None]

    # ------------------------------------------------------------------
    # Candles
    # ------------------------------------------------------------------

    async def list_candles(
        self,
        symbol: str,
        interval: str,
        limit: int,
        since: datetime | None = None,
        instrument_key: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return up to ``limit`` most recent candles, oldest first.

        ``since`` (UTC) restricts the query to bars starting at or after it;
        the live stream uses it to rebuild only the current bar.
        """
        timeframe = get_timeframe(interval)
        match_filter: dict[str, Any] = {"underlying_symbol": symbol}
        instrument = await self._find_active_instrument(symbol, instrument_key)
        if instrument is not None:
            match_filter["instrument_key"] = instrument["instrument_key"]
        elif instrument_key:
            match_filter["instrument_key"] = instrument_key

        if timeframe.source == "1m":
            if timeframe.key == "1m":
                return await self._one_minute_candles(match_filter, limit, since)
            return await self._aggregate_intraday(
                symbol, interval, limit, match_filter, since
            )

        daily = await self._daily_candles(symbol, match_filter, since)
        if timeframe.key != "1d":
            daily = aggregate_candles(daily, timeframe, symbol)
        return daily[-limit:]

    async def _one_minute_candles(
        self, match_filter: dict[str, Any], limit: int, since: datetime | None
    ) -> list[dict[str, Any]]:
        query = dict(match_filter)
        if since is not None:
            query["minute"] = {"$gte": since}
        collection = self.database[get_interval("1m").collection]
        cursor = collection.find(query).sort("minute", DESCENDING).limit(limit)
        documents = await cursor.to_list(length=limit)
        documents.reverse()
        result = [_public_document(item) for item in documents if item is not None]
        for candle in result:
            if candle is not None:
                candle["interval"] = "1m"
                if candle.get("cumulative_volume") is None:
                    candle["cumulative_volume"] = candle.get("volume")
        return result

    async def _aggregate_intraday(
        self,
        symbol: str,
        interval: str,
        limit: int | None,
        match_filter: dict[str, Any],
        since: datetime | None,
    ) -> list[dict[str, Any]]:
        timeframe = TIMEFRAMES[interval]
        query = dict(match_filter)
        if since is not None:
            query["minute"] = {"$gte": since}
        pipeline: list[dict[str, Any]] = [
            {"$match": query},
            {"$sort": {"minute": 1}},
            {
                "$group": {
                    "_id": mongo_bucket_expression(timeframe),
                    "instrument_key": {"$last": "$instrument_key"},
                    "trading_symbol": {"$last": "$trading_symbol"},
                    "underlying_symbol": {"$last": "$underlying_symbol"},
                    "open": {"$first": "$open"},
                    "high": {"$max": "$high"},
                    "low": {"$min": "$low"},
                    "close": {"$last": "$close"},
                    "volume": {"$sum": {"$ifNull": ["$volume", 0]}},
                    "cumulative_volume": {"$last": "$cumulative_volume"},
                    "open_interest": {"$last": "$open_interest"},
                    "tick_count": {"$sum": {"$ifNull": ["$tick_count", 0]}},
                    "updated_at": {"$max": "$updated_at"},
                }
            },
            {"$sort": {"_id": -1}},
        ]
        if limit is not None:
            pipeline.append({"$limit": limit})
        cursor = await self.database.gold_candles_1m.aggregate(pipeline)
        documents = await cursor.to_list(length=limit)
        documents.reverse()
        return [
            {
                "id": f"{item['instrument_key']}:{interval}:{item['_id'].isoformat()}",
                "instrument_key": item["instrument_key"],
                "trading_symbol": item.get("trading_symbol"),
                "underlying_symbol": item.get("underlying_symbol") or symbol,
                "interval": interval,
                "minute": item["_id"],
                "open": item["open"],
                "high": item["high"],
                "low": item["low"],
                "close": item["close"],
                "volume": item.get("volume", 0),
                "cumulative_volume": item.get("cumulative_volume"),
                "open_interest": item.get("open_interest"),
                "tick_count": item.get("tick_count", 0),
                "updated_at": item.get("updated_at") or item["_id"],
            }
            for item in documents
        ]

    async def _daily_candles(
        self,
        symbol: str,
        match_filter: dict[str, Any],
        since: datetime | None,
    ) -> list[dict[str, Any]]:
        """Merge stored Upstox daily candles with days built from live 1m data.

        Completed days come from ``gold_candles_1d`` when available. Days that
        are missing there (typically today) are built from 1m candles.
        """
        day = TIMEFRAMES["1d"]
        query = dict(match_filter)
        if since is not None:
            query["minute"] = {"$gte": since}

        collection = self.database[get_interval("1d").collection]
        stored_documents = await collection.find(query).sort("minute", ASCENDING).to_list(
            length=None
        )
        merged: dict[datetime, dict[str, Any]] = {}
        for document in stored_documents:
            candle = _public_document(document)
            if candle is None:
                continue
            candle["minute"] = _as_utc(candle["minute"])
            candle["interval"] = "1d"
            candle.setdefault("tick_count", 0)
            candle.setdefault("updated_at", candle["minute"])
            merged[candle["minute"]] = candle

        today = bucket_start(datetime.now(timezone.utc), day)
        live_since = since
        if merged:
            day_after_last_stored = max(merged) + timedelta(days=1)
            live_since = max(live_since, day_after_last_stored) if live_since else day_after_last_stored
            live_since = min(live_since, today)

        live_days = await self._aggregate_intraday(
            symbol, "1d", None, match_filter, live_since
        )
        for candle in live_days:
            minute = _as_utc(candle["minute"])
            candle["minute"] = minute
            if minute not in merged or minute >= today:
                merged[minute] = candle

        return [merged[key] for key in sorted(merged)]
