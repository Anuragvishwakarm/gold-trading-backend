from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_historical_repository
from app.core.config import get_settings
from app.repositories.historical_repository import HistoricalRepository
from app.schemas.historical import (
    CandleIntervalName,
    DataQualityResponse,
    HistoricalSyncRequest,
    HistoricalSyncResponse,
    HistoricalSyncStatus,
)
from app.services.historical import HistoricalDataError, HistoricalSyncService


router = APIRouter()


@router.post("/sync", response_model=HistoricalSyncResponse)
async def sync_historical_data(
    request: HistoricalSyncRequest,
    repository: HistoricalRepository = Depends(get_historical_repository),
) -> HistoricalSyncResponse:
    settings = get_settings()
    service = HistoricalSyncService(
        repository=repository,
        access_token=settings.upstox_access_token,
        symbol=settings.gold_underlying_symbol,
    )
    try:
        result = await service.sync(request)
    except HistoricalDataError as exc:
        message = str(exc)
        code = (
            status.HTTP_409_CONFLICT
            if "already running" in message
            else status.HTTP_502_BAD_GATEWAY
        )
        if "instrument is not available" in message:
            code = status.HTTP_404_NOT_FOUND
        if "must be" in message or "completed dates" in message:
            code = status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=code, detail=message) from exc
    return HistoricalSyncResponse.model_validate(result)


@router.get("/sync/latest", response_model=HistoricalSyncStatus)
async def latest_historical_sync(
    repository: HistoricalRepository = Depends(get_historical_repository),
) -> HistoricalSyncStatus:
    document = await repository.get_latest_sync()
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No historical sync has run yet",
        )
    return HistoricalSyncStatus.model_validate(document)


@router.get("/quality", response_model=DataQualityResponse)
async def historical_data_quality(
    interval: CandleIntervalName = Query(default="1m"),
    repository: HistoricalRepository = Depends(get_historical_repository),
) -> DataQualityResponse:
    result = await repository.quality_report(interval)
    return DataQualityResponse.model_validate(result)
