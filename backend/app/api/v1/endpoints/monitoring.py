import time
from typing import Any, Dict

import redis.asyncio as redis
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import require_role
from app.core.config import settings
from app.core.database import get_db_session
from app.domain.user.models import User, UserRole

router = APIRouter()


@router.get("/health/live", response_model=Dict[str, Any])
async def liveness():
    """Kubernetes liveness probe"""
    return {"status": "alive", "timestamp": time.time()}


@router.get("/health/ready", response_model=Dict[str, Any])
async def readiness(db: AsyncSession = Depends(get_db_session)):
    """Kubernetes readiness probe with dependency checks"""
    health_status = {"status": "healthy", "timestamp": time.time(), "checks": {}}

    # Database check
    try:
        await db.execute(text("SELECT 1"))
        health_status["checks"]["database"] = "healthy"
    except Exception as e:
        health_status["checks"]["database"] = f"unhealthy: {str(e)}"
        health_status["status"] = "unhealthy"

    if settings.DEMO_MODE or not settings.REDIS_URL:
        health_status["checks"]["redis"] = "disabled"
    else:
        try:
            r = redis.from_url(settings.REDIS_URL)
            await r.ping()
            await r.aclose()
            health_status["checks"]["redis"] = "healthy"
        except Exception as e:
            health_status["checks"]["redis"] = f"unhealthy: {str(e)}"
            health_status["status"] = "degraded"

    return health_status


@router.get("/health/metrics", response_model=Dict[str, Any])
async def health_metrics(
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db_session),
):
    """Detailed health metrics (admin only — exposes user counts and Redis internals)"""
    metrics = {
        "timestamp": time.time(),
        "uptime_seconds": time.time(),  # Should track actual uptime
        "database": {},
        "redis": {},
    }

    # Database metrics
    try:
        result = await db.execute(text("SELECT count(*) FROM users"))
        user_count = result.scalar()
        metrics["database"]["user_count"] = user_count
        metrics["database"]["status"] = "connected"
    except Exception as e:
        metrics["database"]["status"] = f"error: {str(e)}"

    if settings.DEMO_MODE or not settings.REDIS_URL:
        metrics["redis"]["status"] = "disabled"
    else:
        try:
            r = redis.from_url(settings.REDIS_URL)
            info = await r.info()
            await r.aclose()
            metrics["redis"]["used_memory"] = info.get("used_memory_human", "unknown")
            metrics["redis"]["connected_clients"] = info.get("connected_clients", 0)
            metrics["redis"]["status"] = "connected"
        except Exception as e:
            metrics["redis"]["status"] = f"error: {str(e)}"

    return metrics
