from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_market_repository
from app.repositories.market_repository import MarketRepository
from app.schemas.analytics import AnalyticsInterval
from app.schemas.backtest import BacktestSummaryResponse
from app.services.backtesting import calculate_backtest


router = APIRouter()


@router.get("/summary", response_model=BacktestSummaryResponse)
async def get_backtest_summary(
    interval: AnalyticsInterval = Query(default="5m"),
    horizon_minutes: int = Query(default=15, alias="horizon", ge=1, le=525600),
    limit: int = Query(default=1000, ge=100, le=5000),
    minimum_move_percent: float = Query(default=0.0, ge=0.0, le=10.0),
    recent_limit: int = Query(default=50, ge=1, le=200),
    instrument_key: str | None = Query(default=None, description="Contract; default nearest expiry"),
    repository: MarketRepository = Depends(get_market_repository),
) -> BacktestSummaryResponse:
    candles = await repository.list_candles(
        "GOLD", interval, limit, instrument_key=instrument_key
    )
    if not candles:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Gold candles are available for backtesting",
        )

    try:
        result = calculate_backtest(
            candles=candles,
            interval=interval,
            horizon_minutes=horizon_minutes,
            minimum_move_percent=minimum_move_percent,
            recent_limit=recent_limit,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return BacktestSummaryResponse.model_validate(result)
