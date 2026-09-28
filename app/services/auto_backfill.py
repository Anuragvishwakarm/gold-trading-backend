from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import get_settings
from app.repositories.historical_repository import HistoricalRepository
from app.schemas.historical import HistoricalSyncRequest
from app.services.historical import HistoricalDataError, HistoricalSyncService


logger = logging.getLogger(__name__)


def backfill_plan(
    today: datetime, instrument_key: str | None = None
) -> list[HistoricalSyncRequest]:
    """Completed-day ranges to fetch: 1m for intraday charts, 1d for D/W/M."""
    settings = get_settings()
    yesterday = today.date() - timedelta(days=1)
    return [
        HistoricalSyncRequest(
            intervals=["1m"],
            from_date=yesterday - timedelta(days=settings.auto_backfill_days - 1),
            to_date=yesterday,
            instrument_key=instrument_key,
        ),
        HistoricalSyncRequest(
            intervals=["1d"],
            from_date=yesterday - timedelta(days=settings.auto_backfill_daily_days - 1),
            to_date=yesterday,
            instrument_key=instrument_key,
        ),
    ]


async def automatic_backfill_loop(database: Any) -> None:
    settings = get_settings()
    await asyncio.sleep(settings.auto_backfill_start_delay_seconds)

    while True:
        wait_seconds = settings.auto_backfill_interval_hours * 3600
        try:
            repository = HistoricalRepository(database)
            service = HistoricalSyncService(
                repository=repository,
                access_token=settings.upstox_access_token,
                symbol=settings.gold_underlying_symbol,
            )
            contracts = await repository.list_active_instruments(settings.gold_underlying_symbol)
            keys = [contract["instrument_key"] for contract in contracts] or [None]
            # Every collected contract (Oct, Dec, …) gets its own history.
            for key in keys:
                for request in backfill_plan(datetime.now(timezone.utc), key):
                    result = await service.sync(request)
                    fetched = sum(item["fetched"] for item in result["results"])
                    logger.info(
                        "Automatic Gold backfill %s (%s) completed: %s candles",
                        result.get("trading_symbol"),
                        ",".join(request.intervals),
                        fetched,
                    )
        except asyncio.CancelledError:
            raise
        except HistoricalDataError as exc:
            wait_seconds = settings.auto_backfill_retry_minutes * 60
            logger.warning("Automatic Gold backfill deferred: %s", exc)
        except Exception:
            wait_seconds = settings.auto_backfill_retry_minutes * 60
            logger.exception("Automatic Gold backfill failed")

        await asyncio.sleep(wait_seconds)
