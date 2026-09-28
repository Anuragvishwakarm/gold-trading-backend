from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo import ASCENDING, DESCENDING, UpdateOne

from app.core.intervals import get_interval


class HistoricalRepository:
    def __init__(self, database: Any) -> None:
        self.database = database

    async def get_active_instrument(
        self, symbol: str, instrument_key: str | None = None
    ) -> dict[str, Any] | None:
        if instrument_key:
            return await self.database.instruments.find_one({"instrument_key": instrument_key})
        contracts = await self.list_active_instruments(symbol)
        if contracts:
            return contracts[0]
        return await self.database.instruments.find_one(
            {"$or": [{"underlying_symbol": symbol}, {"name": symbol}]},
            sort=[("updated_at", DESCENDING)],
        )

    async def list_active_instruments(self, symbol: str) -> list[dict[str, Any]]:
        """Non-expired contracts saved by the collector, nearest expiry first."""
        cursor = self.database.instruments.find(
            {
                "$or": [{"underlying_symbol": symbol}, {"name": symbol}],
                "expiry": {"$gte": datetime.now(timezone.utc) - timedelta(days=1)},
            }
        ).sort("expiry", ASCENDING)
        return await cursor.to_list(length=20)

    async def start_sync(self, document: dict[str, Any]) -> None:
        await self.database.historical_sync_logs.insert_one(document)

    async def finish_sync(
        self,
        sync_id: str,
        status: str,
        results: list[dict[str, Any]],
        error: str | None = None,
    ) -> None:
        update: dict[str, Any] = {
            "status": status,
            "results": results,
            "finished_at": datetime.now(timezone.utc),
        }
        if error:
            update["error"] = error
        await self.database.historical_sync_logs.update_one(
            {"sync_id": sync_id}, {"$set": update}
        )

    async def get_latest_sync(self) -> dict[str, Any] | None:
        document = await self.database.historical_sync_logs.find_one(
            sort=[("started_at", DESCENDING)]
        )
        if document:
            document.pop("_id", None)
        return document

    async def upsert_candles(
        self, interval: str, documents: list[dict[str, Any]]
    ) -> tuple[int, int]:
        if not documents:
            return 0, 0
        collection = self.database[get_interval(interval).collection]
        operations = [
            UpdateOne(
                {
                    "instrument_key": document["instrument_key"],
                    "minute": document["minute"],
                },
                {
                    "$set": document,
                    # tick_count only on insert so live candles keep their count.
                    "$setOnInsert": {
                        "created_at": datetime.now(timezone.utc),
                        "tick_count": 0,
                    },
                },
                upsert=True,
            )
            for document in documents
        ]
        result = await collection.bulk_write(operations, ordered=False)
        return result.upserted_count, result.modified_count

    async def quality_report(self, interval: str) -> dict[str, Any]:
        spec = get_interval(interval)
        collection = self.database[spec.collection]
        total = await collection.count_documents({})
        first = await collection.find_one(sort=[("minute", ASCENDING)])
        last = await collection.find_one(sort=[("minute", DESCENDING)])

        invalid_ohlc_filter = {
            "$expr": {
                "$or": [
                    {"$lt": ["$high", "$low"]},
                    {"$lt": ["$high", {"$max": ["$open", "$close"]}]},
                    {"$gt": ["$low", {"$min": ["$open", "$close"]}]},
                ]
            }
        }
        non_positive_filter = {
            "$or": [{field: {"$lte": 0}} for field in ("open", "high", "low", "close")]
        }
        volume_filter = {
            "$or": [
                {"volume": {"$exists": False}},
                {"volume": None},
                {"volume": {"$lt": 0}},
            ]
        }

        invalid_ohlc = await collection.count_documents(invalid_ohlc_filter)
        non_positive = await collection.count_documents(non_positive_filter)
        invalid_volume = await collection.count_documents(volume_filter)
        duplicate_cursor = await collection.aggregate(
            [
                {
                    "$group": {
                        "_id": {
                            "instrument_key": "$instrument_key",
                            "minute": "$minute",
                        },
                        "count": {"$sum": 1},
                    }
                },
                {"$match": {"count": {"$gt": 1}}},
                {"$count": "total"},
            ]
        )
        duplicate_rows = await duplicate_cursor.to_list(length=1)
        duplicates = duplicate_rows[0]["total"] if duplicate_rows else 0
        issues = invalid_ohlc + non_positive + invalid_volume + duplicates
        return {
            "interval": interval,
            "collection": spec.collection,
            "total_candles": total,
            "first_candle_at": first.get("minute") if first else None,
            "last_candle_at": last.get("minute") if last else None,
            "duplicate_groups": duplicates,
            "invalid_ohlc": invalid_ohlc,
            "non_positive_prices": non_positive,
            "missing_or_invalid_volume": invalid_volume,
            "status": "no_data" if total == 0 else ("issues_found" if issues else "ok"),
        }
