from __future__ import annotations

from pymongo import ASCENDING, DESCENDING, AsyncMongoClient

from app.core.config import get_settings
from app.core.intervals import INTERVALS


class MongoDatabase:
    def __init__(self) -> None:
        self.client: AsyncMongoClient | None = None
        self.database = None

    async def connect(self) -> None:
        settings = get_settings()
        self.client = AsyncMongoClient(
            settings.mongodb_uri,
            tz_aware=True,
            serverSelectionTimeoutMS=5000,
        )
        await self.client.admin.command("ping")
        self.database = self.client[settings.mongodb_database]

    async def create_indexes(self) -> None:
        if self.database is None:
            raise RuntimeError("MongoDB is not connected")
        await self.database.gold_ticks.create_index(
            [("instrument_key", ASCENDING), ("received_at", DESCENDING)]
        )
        await self.database.gold_ticks.create_index([("last_traded_at", DESCENDING)])
        # Used by /ticks/latest and the live stream, which poll every second.
        await self.database.gold_ticks.create_index(
            [("underlying_symbol", ASCENDING), ("received_at", DESCENDING)]
        )
        for interval in INTERVALS.values():
            collection = self.database[interval.collection]
            await collection.create_index(
                [("instrument_key", ASCENDING), ("minute", ASCENDING)], unique=True
            )
            await collection.create_index([("minute", DESCENDING)])
            await collection.create_index(
                [("underlying_symbol", ASCENDING), ("minute", DESCENDING)]
            )
        await self.database.instruments.create_index(
            [("instrument_key", ASCENDING)], unique=True
        )
        await self.database.historical_sync_logs.create_index(
            [("sync_id", ASCENDING)], unique=True
        )
        await self.database.historical_sync_logs.create_index(
            [("started_at", DESCENDING)]
        )

    async def ping(self) -> bool:
        if self.client is None:
            return False
        result = await self.client.admin.command("ping")
        return result.get("ok") == 1.0

    async def close(self) -> None:
        if self.client is not None:
            await self.client.close()
        self.client = None
        self.database = None

    def get_database(self):
        if self.database is None:
            raise RuntimeError("MongoDB is not connected")
        return self.database


mongodb = MongoDatabase()
