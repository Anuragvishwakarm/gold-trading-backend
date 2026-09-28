from __future__ import annotations

from app.core.database import mongodb
from app.repositories.historical_repository import HistoricalRepository
from app.repositories.market_repository import MarketRepository


def get_market_repository() -> MarketRepository:
    return MarketRepository(mongodb.get_database())


def get_historical_repository() -> HistoricalRepository:
    return HistoricalRepository(mongodb.get_database())
