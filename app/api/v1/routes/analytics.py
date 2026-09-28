from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_market_repository
from app.repositories.market_repository import MarketRepository
from app.schemas.analytics import (
    AnalyticsInterval,
    AnalyticsResponse,
)
from app.services.technical_indicators import (
    MINIMUM_CANDLES,
    calculate_technical_indicators,
)


router = APIRouter()


@router.get(
    "/indicators",
    response_model=AnalyticsResponse,
)
async def get_technical_indicators(
    interval: AnalyticsInterval = Query(
        default="15m"
    ),
    limit: int = Query(
        default=500,
        ge=50,
        le=5000,
    ),
    ma_type: Literal["sma", "ema"] = Query(
        default="sma"
    ),
    ma_period: int = Query(
        default=20,
        ge=2,
        le=500,
    ),
    instrument_key: str | None = Query(default=None, description="Contract; default nearest expiry"),
    repository: MarketRepository = Depends(
        get_market_repository
    ),
) -> AnalyticsResponse:

    candles = await repository.list_candles(
        "GOLD",
        interval,
        limit,
        instrument_key=instrument_key,
    )

    if not candles:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "No Gold candles are available "
                "for technical analysis"
            ),
        )

    if len(candles) < MINIMUM_CANDLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Technical analysis needs at least {MINIMUM_CANDLES} "
                f"{interval} candles; only {len(candles)} are available"
            ),
        )

    try:
        result = calculate_technical_indicators(
            candles,
            interval,
            ma_type=ma_type,
            ma_period=ma_period,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return AnalyticsResponse.model_validate(result)