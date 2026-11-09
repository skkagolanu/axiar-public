from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user, require_role
from app.core.database import get_db_session
from app.domain.booking.repository import BookingRepository
from app.domain.booking.schemas import BookingRead as BookingResponse
from app.domain.dispatch.repository import DispatchRepository
from app.domain.dispatch.service import DispatchService
from app.domain.provider.repository import ProviderRepository
from app.domain.user.models import User, UserRole
from app.services.route_optimization import RouteOptimizationService

router = APIRouter()


async def _ensure_provider_owns_booking(db, current_user, booking):
    """Providers may only act on their own bookings. booking.provider_id is a Provider.id,
    so resolve the caller's provider profile rather than comparing against User.id."""
    if current_user.role == UserRole.PROVIDER:
        provider = await ProviderRepository(db).get_by_user_id(current_user.id)
        if not provider or booking.provider_id != provider.id:
            raise HTTPException(status_code=403, detail="Access denied")


@router.post("/{booking_id}/auto-assign", response_model=BookingResponse)
async def auto_assign_agent(
    booking_id: UUID,
    current_user: User = Depends(require_role([UserRole.PROVIDER, UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db_session),
):
    """Auto-assign best field agent to booking using AI"""
    booking_repo = BookingRepository(db)
    booking = await booking_repo.get_by_id(booking_id)

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    await _ensure_provider_owns_booking(db, current_user, booking)

    if booking.field_agent_id:
        raise HTTPException(status_code=400, detail="Booking already has an assigned agent")

    dispatch_repo = DispatchRepository(db)
    dispatch_service = DispatchService(dispatch_repo)

    best_agent_id = await dispatch_service.find_best_agent(
        latitude=booking.location_coordinates.latitude if booking.location_coordinates else 51.5074,
        longitude=booking.location_coordinates.longitude if booking.location_coordinates else -0.1278,
        service_type="general",
        required_skills=None,
    )

    if not best_agent_id:
        raise HTTPException(status_code=404, detail="No available agents found")

    updated_booking = await dispatch_service.assign_agent(booking_id, best_agent_id)
    await db.commit()

    return updated_booking


@router.post("/{booking_id}/assign/{agent_id}", response_model=BookingResponse)
async def manual_assign_agent(
    booking_id: UUID,
    agent_id: UUID,
    current_user: User = Depends(require_role([UserRole.PROVIDER, UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db_session),
):
    """Manually assign field agent to booking"""
    booking_repo = BookingRepository(db)
    booking = await booking_repo.get_by_id(booking_id)

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    await _ensure_provider_owns_booking(db, current_user, booking)

    dispatch_repo = DispatchRepository(db)
    dispatch_service = DispatchService(dispatch_repo)

    updated_booking = await dispatch_service.assign_agent(booking_id, agent_id)
    await db.commit()

    return updated_booking


class RouteStop(BaseModel):
    id: str
    lat: float
    lng: float
    label: Optional[str] = None


class OptimizeRouteRequest(BaseModel):
    stops: List[RouteStop]


@router.post("/optimize", response_model=Dict[str, Any])
async def optimize_route(
    payload: OptimizeRouteRequest,
    current_user: User = Depends(require_role([UserRole.PROVIDER, UserRole.ADMIN])),
):
    """
    Optimize the visiting order for a list of stops using OR-Tools TSP solver.
    Falls back to the input order when OR-Tools is not installed.
    """
    stops_dicts = [{"id": s.id, "latitude": s.lat, "longitude": s.lng, "label": s.label} for s in payload.stops]
    service = RouteOptimizationService()
    result = await service.optimize_route(stops_dicts)
    return result
