from datetime import date, datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user
from app.core.database import get_db_session
from app.domain.user.models import User
from app.services.ai_scheduling import AISchedulingService

router = APIRouter(prefix="/ai/scheduling", tags=["AI Scheduling"])


@router.get("/suggestions", response_model=Dict[str, Any])
async def get_scheduling_suggestions(
    schedule_date: date = Query(..., description="Date to generate suggestions for"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get AI-powered scheduling suggestions for a specific date"""
    service = AISchedulingService(db)
    suggestions = await service.suggest_optimal_schedule(
        datetime.combine(schedule_date, datetime.min.time()), current_user.tenant_id
    )
    return suggestions


@router.post("/auto-assign", response_model=Dict[str, Any])
async def auto_assign_bookings(
    schedule_date: date = Query(..., description="Date to auto-assign bookings"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Automatically assign bookings based on AI suggestions"""
    service = AISchedulingService(db)
    result = await service.auto_assign_bookings(datetime.combine(schedule_date, datetime.min.time()), current_user.tenant_id)
    return result
