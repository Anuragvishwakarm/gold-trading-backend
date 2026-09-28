from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_market_repository
from app.core.intervals import TimeframeName
from app.repositories.market_repository import MarketRepository
from app.schemas.market import CandleResponse, InstrumentResponse, TickResponse


router = APIRouter()


@router.get("/instruments", response_model=list[InstrumentResponse])
async def list_instruments(
    repository: MarketRepository = Depends(get_market_repository),
) -> list[InstrumentResponse]:
    """Every collected GOLD future that has not expired, nearest expiry first."""
    documents = await repository.list_instruments("GOLD")
    return [InstrumentResponse.model_validate(item) for item in documents]


@router.get("/instrument", response_model=InstrumentResponse)
async def get_active_instrument(
    instrument_key: str | None = Query(
        default=None,
        description="Contract, e.g. MCX_FO|454818. Default: nearest expiry.",
    ),
    repository: MarketRepository = Depends(get_market_repository),
) -> InstrumentResponse:
    document = await repository.get_active_instrument("GOLD", instrument_key)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gold instrument is not available. Start the collector first.",
        )
    return InstrumentResponse.model_validate(document)


@router.get("/ticks/latest", response_model=TickResponse)
async def get_latest_tick(
    instrument_key: str | None = Query(
        default=None,
        description="Contract, e.g. MCX_FO|454818. Default: nearest expiry.",
    ),
    repository: MarketRepository = Depends(get_market_repository),
) -> TickResponse:
    document = await repository.get_latest_tick("GOLD", instrument_key)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Gold ticks are available",
        )
    return TickResponse.model_validate(document)


@router.get("/ticks", response_model=list[TickResponse])
async def list_ticks(
    limit: int = Query(default=100, ge=1, le=1000),
    instrument_key: str | None = Query(
        default=None,
        description="Contract, e.g. MCX_FO|454818. Default: nearest expiry.",
    ),
    repository: MarketRepository = Depends(get_market_repository),
) -> list[TickResponse]:
    documents = await repository.list_ticks("GOLD", limit, instrument_key)
    return [TickResponse.model_validate(item) for item in documents]


@router.get("/candles", response_model=list[CandleResponse])
async def list_candles(
    interval: TimeframeName = Query(
        default="15m",
        description="1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w or 1mo (month)",
    ),
    limit: int = Query(default=500, ge=1, le=5000),
    instrument_key: str | None = Query(
        default=None,
        description="Contract, e.g. MCX_FO|454818. Default: nearest expiry.",
    ),
    repository: MarketRepository = Depends(get_market_repository),
) -> list[CandleResponse]:
    documents = await repository.list_candles(
        "GOLD", interval, limit, instrument_key=instrument_key
    )
    return [CandleResponse.model_validate(item) for item in documents]
