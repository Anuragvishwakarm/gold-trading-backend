from __future__ import annotations

import logging
import queue
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING, DESCENDING, MongoClient, UpdateOne


logger = logging.getLogger(__name__)


class MongoMarketWriter:
    def __init__(
        self,
        uri: str,
        database: str,
        batch_size: int,
        flush_seconds: float,
        queue_max_size: int,
    ) -> None:
        self.client = MongoClient(uri, tz_aware=True, serverSelectionTimeoutMS=5000)
        self.client.admin.command("ping")
        db = self.client[database]
        self.ticks = db.gold_ticks
        self.candles = db.gold_candles_1m
        self.instruments = db.instruments
        self.batch_size = batch_size
        self.flush_seconds = flush_seconds
        self.queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=queue_max_size)
        self._last_cumulative_volume: dict[str, int] = {}
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="mongo-writer", daemon=True)
        self._create_indexes()

    def _create_indexes(self) -> None:
        self.ticks.create_index([("instrument_key", ASCENDING), ("received_at", DESCENDING)])
        self.ticks.create_index([("last_traded_at", DESCENDING)])
        self.candles.create_index(
            [("instrument_key", ASCENDING), ("minute", ASCENDING)], unique=True
        )
        self.instruments.create_index([("instrument_key", ASCENDING)], unique=True)

    def save_instrument(self, instrument: dict[str, Any]) -> None:
        self.instruments.update_one(
            {"instrument_key": instrument["instrument_key"]},
            {"$set": {**instrument, "updated_at": datetime.now(timezone.utc)}},
            upsert=True,
        )

    def start(self) -> None:
        self.thread.start()

    def submit(self, document: dict[str, Any]) -> None:
        try:
            self.queue.put(document, timeout=2)
        except queue.Full:
            logger.error("Mongo write queue is full; dropping one market tick")

    def close(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=max(5.0, self.flush_seconds * 3))
        self.client.close()

    def _run(self) -> None:
        batch: list[dict[str, Any]] = []
        last_flush = time.monotonic()
        while not self.stop_event.is_set() or not self.queue.empty():
            timeout = max(0.05, self.flush_seconds - (time.monotonic() - last_flush))
            try:
                batch.append(self.queue.get(timeout=timeout))
            except queue.Empty:
                pass

            if batch and (
                len(batch) >= self.batch_size
                or time.monotonic() - last_flush >= self.flush_seconds
                or (self.stop_event.is_set() and self.queue.empty())
            ):
                self._flush(batch)
                batch = []
                last_flush = time.monotonic()

    def _flush(self, batch: list[dict[str, Any]]) -> None:
        try:
            self.ticks.insert_many(batch, ordered=False)
            operations = self._candle_operations(batch)
            if operations:
                self.candles.bulk_write(operations, ordered=False)
            logger.info("Saved %s Gold tick(s)", len(batch))
        except Exception:
            logger.exception("MongoDB batch write failed")

    def _candle_operations(self, batch: list[dict[str, Any]]) -> list[UpdateOne]:
        grouped: dict[
            tuple[str, datetime], list[tuple[dict[str, Any], int]]
        ] = defaultdict(list)
        for tick in batch:
            event_time = tick.get("last_traded_at") or tick.get("feed_timestamp") or tick["received_at"]
            minute = event_time.astimezone(timezone.utc).replace(second=0, microsecond=0)
            instrument_key = tick["instrument_key"]
            current_volume = tick.get("volume_traded_today")
            previous_volume = self._last_cumulative_volume.get(instrument_key)
            volume_delta = 0
            if current_volume is not None:
                current_volume = int(current_volume)
                if previous_volume is not None and current_volume >= previous_volume:
                    volume_delta = current_volume - previous_volume
                self._last_cumulative_volume[instrument_key] = current_volume
            grouped[(instrument_key, minute)].append((tick, volume_delta))

        operations: list[UpdateOne] = []
        for (instrument_key, minute), tick_rows in grouped.items():
            ticks = [row[0] for row in tick_rows]
            interval_volume = sum(row[1] for row in tick_rows)
            prices = [tick["ltp"] for tick in ticks]
            first, last = ticks[0], ticks[-1]
            operations.append(
                UpdateOne(
                    {"instrument_key": instrument_key, "minute": minute},
                    {
                        "$setOnInsert": {
                            "open": first["ltp"],
                            "created_at": datetime.now(timezone.utc),
                            "trading_symbol": first.get("trading_symbol"),
                            "underlying_symbol": first.get("underlying_symbol", "GOLD"),
                            "interval": "1m",
                        },
                        "$min": {"low": min(prices)},
                        "$max": {"high": max(prices)},
                        "$set": {
                            "close": last["ltp"],
                            "last_traded_at": last.get("last_traded_at"),
                            "cumulative_volume": last.get("volume_traded_today"),
                            "open_interest": last.get("open_interest"),
                            "updated_at": datetime.now(timezone.utc),
                        },
                        "$inc": {
                            "tick_count": len(ticks),
                            "volume": interval_volume,
                        },
                    },
                    upsert=True,
                )
            )
        return operations
