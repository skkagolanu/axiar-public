from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user
from app.core.analytics import analytics
from app.core.database import get_db_session
from app.domain.booking.repository import BookingRepository
from app.domain.user.models import User

router = APIRouter()


@router.get("/analytics/demand-forecast", response_model=Dict[str, Any])
async def get_demand_forecast(
    provider_id: UUID,
    days: int = 7,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Get demand forecast (heuristic — per-weekday average booking count, not a trained model)."""
    try:
        repo = BookingRepository(session)
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        bookings = await repo.get_by_provider(provider_id, limit=1000)
        historical = [{"scheduled_time": b.scheduled_time} for b in bookings if b.scheduled_time > cutoff]
        return analytics.forecast_demand(historical)
    except Exception as e:
        return {"error": str(e), "details": "Demand forecast failed"}


@router.post("/analytics/no-show-prediction", response_model=Dict[str, Any])
async def predict_no_show(booking_data: dict, current_user: User = Depends(get_current_user)):
    """Predict no-show probability (heuristic — weighted rules over advance-booking time/first-booking/price, not a trained model)."""
    return analytics.predict_no_show(booking_data)


@router.post("/analytics/dynamic-pricing", response_model=Dict[str, Any])
async def get_dynamic_pricing(
    booking_data: dict,
    provider_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Get dynamic pricing suggestion (heuristic — demand-based surge, not a trained model)."""
    repo = BookingRepository(session)

    # Get demand forecast
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    bookings = await repo.get_by_provider(provider_id, limit=1000)
    historical = [{"scheduled_time": b.scheduled_time} for b in bookings if b.scheduled_time > cutoff]

    demand_forecast = analytics.forecast_demand(historical)
    return analytics.suggest_dynamic_pricing(booking_data, demand_forecast)


@router.get("/analytics/resource-optimization", response_model=Dict[str, Any])
async def optimize_resources(
    provider_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Get resource allocation recommendations (heuristic — rule-based allocation, not a trained model or solver)."""
    try:
        repo = BookingRepository(session)
        bookings = await repo.get_by_provider(provider_id, limit=100)
        upcoming = [{"scheduled_time": b.scheduled_time} for b in bookings if b.scheduled_time > datetime.now(timezone.utc)]
        agents = [{"id": i} for i in range(5)]
        return analytics.optimize_resource_allocation(upcoming, agents)
    except Exception as e:
        return {"error": str(e), "details": "Resource optimization failed"}


@router.get("/analytics/dashboard", response_model=Dict[str, Any])
async def get_dashboard(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Get analytics dashboard summary"""
    try:
        repo = BookingRepository(session)
        from sqlalchemy import func, select

        from app.domain.booking.models import Booking, BookingStatus

        # Get basic stats — scoped to current tenant
        total = await session.execute(select(func.count(Booking.id)).where(Booking.tenant_id == current_user.tenant_id))
        pending = await session.execute(
            select(func.count(Booking.id)).where(
                Booking.tenant_id == current_user.tenant_id,
                Booking.status == BookingStatus.PENDING,
            )
        )
        completed = await session.execute(
            select(func.count(Booking.id)).where(
                Booking.tenant_id == current_user.tenant_id,
                Booking.status == BookingStatus.COMPLETED,
            )
        )

        return {
            "total_bookings": total.scalar() or 0,
            "pending_bookings": pending.scalar() or 0,
            "completed_bookings": completed.scalar() or 0,
            "status": "operational",
        }
    except Exception as e:
        return {"error": str(e), "total_bookings": 0}
