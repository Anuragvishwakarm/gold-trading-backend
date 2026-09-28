from fastapi import APIRouter

from app.api.v1.routes import analytics, backtest, health, historical, market, stream


api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["Health"])
api_router.include_router(market.router, prefix="/market", tags=["Gold Market Data"])
api_router.include_router(stream.router, prefix="/market", tags=["Gold Live Stream"])
api_router.include_router(
    historical.router, prefix="/historical", tags=["Gold Historical Data"]
)
api_router.include_router(
    analytics.router, prefix="/analytics", tags=["Gold Technical Analytics"]
)
api_router.include_router(
    backtest.router, prefix="/backtest", tags=["Gold Signal Backtesting"]
)
