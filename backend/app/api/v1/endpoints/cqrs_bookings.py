from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies.auth import get_current_user
from app.core.cqrs.commands import command_bus
from app.core.cqrs.queries import query_bus
from app.domain.booking.commands import (
    CreateBookingCommand,
    CreateBookingHandler,
    UpdateBookingStatusCommand,
    UpdateBookingStatusHandler,
)
from app.domain.booking.queries import (
    GetBookingHandler,
    GetBookingQuery,
    GetCustomerBookingsHandler,
    GetCustomerBookingsQuery,
    GetProviderBookingsHandler,
    GetProviderBookingsQuery,
)
from app.domain.booking.schemas import BookingCreate
from app.domain.user.models import User

router = APIRouter()

# Register handlers
command_bus.register(CreateBookingCommand, CreateBookingHandler())
command_bus.register(UpdateBookingStatusCommand, UpdateBookingStatusHandler())
query_bus.register(GetBookingQuery, GetBookingHandler())
query_bus.register(GetCustomerBookingsQuery, GetCustomerBookingsHandler())
query_bus.register(GetProviderBookingsQuery, GetProviderBookingsHandler())


@router.post("/cqrs", response_model=Dict[str, Any])
async def create_booking_cqrs(
    booking: BookingCreate,
    current_user: User = Depends(get_current_user),
):
    """Create booking using CQRS"""
    command = CreateBookingCommand(customer_id=current_user.id, **booking.model_dump())
    booking_id = await command_bus.execute(command)
    return {"booking_id": str(booking_id)}


@router.get("/cqrs/{booking_id}", response_model=Dict[str, Any])
async def get_booking_cqrs(booking_id: UUID, current_user: User = Depends(get_current_user)):
    """Get booking using CQRS"""
    query = GetBookingQuery(booking_id=booking_id)
    result = await query_bus.execute(query)
    if not result:
        raise HTTPException(status_code=404, detail="Booking not found")
    return result.model_dump() if result else None


@router.get("/cqrs/customer/{customer_id}", response_model=Dict[str, Any])
async def get_customer_bookings_cqrs(
    customer_id: UUID, limit: int = Query(50, ge=1, le=500), current_user: User = Depends(get_current_user)
):
    """Get customer bookings using CQRS"""
    query = GetCustomerBookingsQuery(customer_id=customer_id, limit=limit)
    results = await query_bus.execute(query)
    return {"bookings": [r.model_dump() for r in results]}


@router.get("/cqrs/provider/{provider_id}", response_model=Dict[str, Any])
async def get_provider_bookings_cqrs(
    provider_id: UUID, limit: int = Query(50, ge=1, le=500), current_user: User = Depends(get_current_user)
):
    """Get provider bookings using CQRS"""
    query = GetProviderBookingsQuery(provider_id=provider_id, limit=limit)
    results = await query_bus.execute(query)
    return {"bookings": [r.model_dump() for r in results]}
