from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import httpx

from app.core.intervals import get_interval
from app.repositories.historical_repository import HistoricalRepository
from app.schemas.historical import HistoricalSyncRequest


UPSTOX_HISTORICAL_URL = "https://api.upstox.com/v3/historical-candle"


class HistoricalDataError(RuntimeError):
    pass


def date_chunks(start: date, end: date, max_days: int) -> list[tuple[date, date]]:
    chunks: list[tuple[date, date]] = []
    current = start
    while current <= end:
        chunk_end = min(current + timedelta(days=max_days - 1), end)
        chunks.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)
    return chunks


def parse_candle(
    row: list[Any], instrument: dict[str, Any], interval: str
) -> dict[str, Any] | None:
    if len(row) < 7:
        return None
    timestamp = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
    timestamp = timestamp.astimezone(timezone.utc)
    open_price, high, low, close = map(float, row[1:5])
    if min(open_price, high, low, close) <= 0:
        return None
    if high < max(open_price, close) or low > min(open_price, close) or high < low:
        return None
    return {
        "instrument_key": instrument["instrument_key"],
        "trading_symbol": instrument.get("trading_symbol"),
        "underlying_symbol": instrument.get("underlying_symbol", "GOLD"),
        "interval": interval,
        "minute": timestamp,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": int(row[5] or 0),
        "open_interest": int(row[6]) if row[6] is not None else None,
        "source": "upstox_historical_v3",
        "updated_at": datetime.now(timezone.utc),
    }


class HistoricalSyncService:
    _lock = asyncio.Lock()

    def __init__(
        self,
        repository: HistoricalRepository,
        access_token: str,
        symbol: str = "GOLD",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.repository = repository
        self.access_token = access_token
        self.symbol = symbol
        self.client = client

    async def sync(self, request: HistoricalSyncRequest) -> dict[str, Any]:
        if not self.access_token:
            raise HistoricalDataError("UPSTOX_ACCESS_TOKEN is missing in .env")
        if self._lock.locked():
            raise HistoricalDataError("A historical sync is already running")

        today = datetime.now(timezone.utc).date()
        to_date = request.to_date or (today - timedelta(days=1))
        from_date = request.from_date or (to_date - timedelta(days=179))
        if to_date >= today:
            raise HistoricalDataError(
                "Historical sync supports completed dates only; to_date must be before today"
            )
        if from_date > to_date:
            raise HistoricalDataError("from_date must be on or before to_date")

        async with self._lock:
            instrument = await self.repository.get_active_instrument(
                self.symbol, request.instrument_key
            )
            if instrument is None:
                raise HistoricalDataError(
                    "Gold instrument is not available. Start the collector first."
                )
            sync_id = str(uuid4())
            started_at = datetime.now(timezone.utc)
            log = {
                "sync_id": sync_id,
                "status": "running",
                "instrument_key": instrument["instrument_key"],
                "trading_symbol": instrument.get("trading_symbol"),
                "from_date": from_date.isoformat(),
                "to_date": to_date.isoformat(),
                "intervals": request.intervals,
                "started_at": started_at,
                "results": [],
            }
            await self.repository.start_sync(log)
            results: list[dict[str, Any]] = []
            try:
                for interval in request.intervals:
                    results.append(
                        await self._sync_interval(
                            instrument, interval, from_date, to_date
                        )
                    )
                await self.repository.finish_sync(sync_id, "completed", results)
            except Exception as exc:
                message = str(exc)[:1000]
                await self.repository.finish_sync(sync_id, "failed", results, message)
                if isinstance(exc, HistoricalDataError):
                    raise
                raise HistoricalDataError(message) from exc

            return {
                **log,
                "status": "completed",
                "results": results,
                "finished_at": datetime.now(timezone.utc),
            }

    async def _sync_interval(
        self,
        instrument: dict[str, Any],
        interval: str,
        from_date: date,
        to_date: date,
    ) -> dict[str, Any]:
        spec = get_interval(interval)
        fetched = upserted = modified = request_count = 0
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=30.0)
        try:
            for chunk_start, chunk_end in date_chunks(
                from_date, to_date, spec.max_days_per_request
            ):
                rows = await self._fetch_rows(
                    client,
                    instrument["instrument_key"],
                    spec.unit,
                    spec.value,
                    chunk_start,
                    chunk_end,
                )
                request_count += 1
                documents = [
                    candle
                    for row in rows
                    if (candle := parse_candle(row, instrument, interval)) is not None
                ]
                fetched += len(documents)
                inserted, changed = await self.repository.upsert_candles(
                    interval, documents
                )
                upserted += inserted
                modified += changed
        finally:
            if owns_client:
                await client.aclose()
        return {
            "interval": interval,
            "fetched": fetched,
            "upserted": upserted,
            "modified": modified,
            "requests": request_count,
        }

    async def _fetch_rows(
        self,
        client: httpx.AsyncClient,
        instrument_key: str,
        unit: str,
        interval: int,
        from_date: date,
        to_date: date,
    ) -> list[list[Any]]:
        encoded_key = quote(instrument_key, safe="")
        url = (
            f"{UPSTOX_HISTORICAL_URL}/{encoded_key}/{unit}/{interval}/"
            f"{to_date.isoformat()}/{from_date.isoformat()}"
        )
        response = await client.get(
            url,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Accept": "application/json",
            },
        )
        if response.status_code >= 400:
            detail = response.text[:500]
            raise HistoricalDataError(
                f"Upstox historical API returned {response.status_code}: {detail}"
            )
        payload = response.json()
        if payload.get("status") != "success":
            raise HistoricalDataError("Upstox historical API returned an invalid response")
        return payload.get("data", {}).get("candles", [])
