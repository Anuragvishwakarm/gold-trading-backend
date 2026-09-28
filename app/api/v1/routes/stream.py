"""Browser-facing live stream.

``WS /api/v1/market/stream?interval=15m&instrument_key=MCX_FO|...``

The collector writes ticks to MongoDB about once a second. This endpoint
watches for the newest tick and pushes it to the browser together with the
*current* candle for the requested timeframe, so the chart can update its
last bar without reloading history.

Messages (JSON):

* ``{"type": "snapshot" | "update", "interval", "tick", "candle"}``
* ``{"type": "heartbeat", "server_time"}`` when no new tick arrived for a while
* ``{"type": "error", "detail"}`` for an invalid interval (then closed)

Polling MongoDB (instead of change streams) keeps this working on the
standalone MongoDB used in development, which has no replica set.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status

from app.api.dependencies import get_market_repository
from app.core.config import get_settings
from app.core.intervals import TIMEFRAMES
from app.repositories.market_repository import MarketRepository
from app.schemas.market import CandleResponse, TickResponse
from app.services.candles import bucket_start


logger = logging.getLogger(__name__)
router = APIRouter()


def _tick_time(tick: dict[str, Any]) -> datetime:
    value = tick.get("last_traded_at") or tick.get("received_at")
    if value is None:
        return datetime.now(timezone.utc)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


async def build_update(
    repository: MarketRepository,
    interval: str,
    tick: dict[str, Any],
    kind: str,
    instrument_key: str | None = None,
) -> dict[str, Any]:
    timeframe = TIMEFRAMES[interval]
    since = bucket_start(_tick_time(tick), timeframe)
    candles = await repository.list_candles(
        "GOLD", interval, 1, since=since, instrument_key=instrument_key or tick.get("instrument_key")
    )
    return {
        "type": kind,
        "interval": interval,
        "tick": TickResponse.model_validate(tick).model_dump(mode="json"),
        "candle": (
            CandleResponse.model_validate(candles[-1]).model_dump(mode="json")
            if candles
            else None
        ),
    }


@router.websocket("/stream")
async def market_stream(
    websocket: WebSocket,
    interval: str = "15m",
    instrument_key: str | None = None,
    repository: MarketRepository = Depends(get_market_repository),
) -> None:
    settings = get_settings()
    await websocket.accept()

    if interval not in TIMEFRAMES:
        await websocket.send_json(
            {"type": "error", "detail": f"Unsupported interval: {interval}"}
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    last_tick_id: str | None = None
    last_sent = time.monotonic()
    try:
        while True:
            tick = await repository.get_latest_tick("GOLD", instrument_key)
            if tick is not None and tick["id"] != last_tick_id:
                kind = "snapshot" if last_tick_id is None else "update"
                await websocket.send_json(
                    await build_update(repository, interval, tick, kind, instrument_key)
                )
                last_tick_id = tick["id"]
                last_sent = time.monotonic()
            elif time.monotonic() - last_sent >= settings.stream_heartbeat_seconds:
                await websocket.send_json(
                    {
                        "type": "heartbeat",
                        "server_time": datetime.now(timezone.utc).isoformat(),
                    }
                )
                last_sent = time.monotonic()
            await asyncio.sleep(settings.stream_poll_seconds)
    except (WebSocketDisconnect, asyncio.CancelledError):
        return
    except Exception as exc:  # connection closed mid-send, Mongo errors, ...
        logger.info("Live stream closed: %s", exc)
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except Exception:
            pass
