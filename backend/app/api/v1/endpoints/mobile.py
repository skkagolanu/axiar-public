from datetime import datetime
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user
from app.core.database import get_db_session
from app.domain.booking.repository import BookingRepository
from app.domain.user.models import User

router = APIRouter()


class MobileBookingResponse(BaseModel):
    """Optimized booking response for mobile"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider_name: str
    service_name: str
    scheduled_time: datetime
    status: str
    location_postcode: str


class MobileDashboardResponse(BaseModel):
    """Mobile dashboard with minimal data"""

    upcoming_bookings: List[MobileBookingResponse]
    active_count: int
    completed_count: int


@router.get("/dashboard", response_model=MobileDashboardResponse)
async def get_mobile_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get optimized dashboard for mobile app"""
    booking_repo = BookingRepository(db)
    bookings = await booking_repo.get_by_customer(current_user.id, limit=10)

    upcoming = [
        MobileBookingResponse(
            id=b.id,
            provider_name=b.provider.business_name if b.provider else "Unknown Provider",
            service_name=b.service.name if b.service else "Unknown Service",
            scheduled_time=b.scheduled_time,
            status=b.status.value,
            location_postcode=b.location_postcode,
        )
        for b in bookings[:5]
    ]

    return MobileDashboardResponse(upcoming_bookings=upcoming, active_count=len(bookings), completed_count=0)
