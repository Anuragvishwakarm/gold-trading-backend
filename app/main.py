from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from contextlib import suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.database import mongodb
from app.services.auto_backfill import automatic_backfill_loop


settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await mongodb.connect()
    await mongodb.create_indexes()
    backfill_task: asyncio.Task[None] | None = None
    if settings.auto_historical_backfill:
        backfill_task = asyncio.create_task(
            automatic_backfill_loop(mongodb.get_database()),
            name="gold-automatic-backfill",
        )
    try:
        yield
    finally:
        if backfill_task is not None:
            backfill_task.cancel()
            with suppress(asyncio.CancelledError):
                await backfill_task
        await mongodb.close()


app = FastAPI(
    title=settings.app_name,
    version="2.0.0",
    description="MCX Gold live and historical market-data API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/", tags=["Application"])
async def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "version": "2.0.0",
        "docs": "/docs",
        "api": settings.api_v1_prefix,
    }
