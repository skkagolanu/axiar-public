from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user, require_role
from app.core.database import get_db_session
from app.domain.payment.schedule_repository import PaymentScheduleRepository
from app.domain.payment.schedule_schemas import (
    CreateScheduleRequest,
    PaymentScheduleRead,
)
from app.domain.user.models import User, UserRole

router = APIRouter()


@router.post("/schedules", response_model=list[PaymentScheduleRead])
async def create_payment_schedule(
    request: CreateScheduleRequest,
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.PROVIDER])),
    session: AsyncSession = Depends(get_db_session),
):
    """Create payment schedule with milestones"""
    repo = PaymentScheduleRepository(session)
    schedules = await repo.create_schedule(request.booking_id, request.milestones)
    await session.commit()
    return schedules


@router.get("/schedules/booking/{booking_id}", response_model=list[PaymentScheduleRead])
async def get_booking_schedule(
    booking_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Get payment schedule for booking"""
    repo = PaymentScheduleRepository(session)
    return await repo.get_by_booking(booking_id)


@router.get("/schedules/overdue", response_model=list[PaymentScheduleRead])
async def get_overdue_schedules(
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.PROVIDER])),
    session: AsyncSession = Depends(get_db_session),
):
    """Get overdue payment schedules"""
    repo = PaymentScheduleRepository(session)
    return await repo.get_overdue()


@router.post("/schedules/{schedule_id}/mark-paid", response_model=Dict[str, Any])
async def mark_schedule_paid(
    schedule_id: UUID,
    payment_id: UUID,
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.PROVIDER])),
    session: AsyncSession = Depends(get_db_session),
):
    """Mark payment schedule as paid"""
    repo = PaymentScheduleRepository(session)
    schedule = await repo.mark_paid(schedule_id, payment_id)

    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    await session.commit()
    return {"status": "success", "schedule_id": str(schedule_id)}
