from fastapi import APIRouter, HTTPException, status

from app.core.database import mongodb


router = APIRouter()


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> dict[str, str]:
    if not await mongodb.ping():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MongoDB is not ready",
        )
    return {"status": "ready", "mongodb": "connected"}

