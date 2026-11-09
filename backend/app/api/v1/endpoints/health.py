import logging
from typing import Dict

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_session
from app.core.schemas import HealthResponse

router = APIRouter(tags=["Health"])
logger = logging.getLogger(__name__)


@router.get("/health", response_model=Dict[str, str])
async def health():
    """Simple heartbeat endpoint"""
    return {"status": "healthy"}


@router.get("/ready", response_model=HealthResponse)
async def readiness(session: AsyncSession = Depends(get_db_session)):
    """Detailed readiness check for load balancers"""
    checks = {"database": "down", "cache": "down"}

    try:
        # Check database
        await session.execute(text("SELECT 1"))
        checks["database"] = "up"
    except Exception as e:
        logger.error(f"Database check failed: {e}")

    try:
        # Check cache (Redis)
        from app.core.cache import cache_manager as cache

        is_healthy = await cache.health_check()
        checks["cache"] = "up" if is_healthy else "down"
        if not is_healthy:
            logger.warning("Redis health check failed")
    except Exception as e:
        logger.error(f"Cache check failed: {e}")
        checks["cache"] = "down"

    all_healthy = all(v == "up" for v in checks.values())

    return {
        "status": "ready" if all_healthy else "degraded",
        "version": settings.VERSION,
        "database": checks["database"],
        "cache": checks["cache"],
    }
