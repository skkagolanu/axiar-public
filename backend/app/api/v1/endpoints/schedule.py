from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import security_manager
from app.core.tenant_context import set_current_tenant
from app.domain.booking.models import Booking, BookingStatus, FieldAgent, PaymentTiming, Provider, Service
from app.domain.booking.repository import BookingRepository
from app.domain.user.models import User, UserRole

router = APIRouter()

from app.api.dependencies.auth import get_current_user


@router.get("/schedule")
async def get_schedule(session: AsyncSession = Depends(get_db_session), current_user: User = Depends(get_current_user)):
    """Get schedule events"""
    # Get all bookings with an assigned agent
    query = (
        select(Booking, Service)
        .join(Service, Booking.service_id == Service.id)
        .where(Booking.field_agent_id.is_not(None), Booking.tenant_id == current_user.tenant_id)
    )
    result = await session.execute(query)
    rows = result.all()

    events = []
    for booking, service in rows:
        events.append(
            {
                "id": str(booking.id),
                "resourceId": str(booking.field_agent_id),
                "startTime": booking.scheduled_time.isoformat(),
                # approx end time
                "endTime": (
                    booking.scheduled_time
                    + (timedelta(minutes=booking.duration_minutes) if booking.duration_minutes else timedelta(hours=1))
                ).isoformat(),
                "title": f"{service.name} - {booking.location_postcode}",
                "status": booking.status.value if hasattr(booking.status, "value") else booking.status,
                "type": service.service_type,
            }
        )
    return events


@router.get("/jobs")
async def get_jobs(session: AsyncSession = Depends(get_db_session), current_user: User = Depends(get_current_user)):
    """Get pending jobs"""
    # Join Booking -> User (Customer), Service
    query = (
        select(Booking, User, Service)
        .join(User, Booking.customer_id == User.id)
        .join(Service, Booking.service_id == Service.id)
        .where(Booking.status == BookingStatus.PENDING, Booking.tenant_id == current_user.tenant_id)
    )
    result = await session.execute(query)
    rows = result.all()

    jobs = []
    for booking, customer, service in rows:
        jobs.append(
            {
                "id": str(booking.id),
                "customerName": f"{customer.first_name} {customer.last_name}".strip(),
                "customerPhone": customer.phone or "N/A",
                "address": booking.location_address or booking.location_postcode,
                "serviceType": service.name,
                "description": booking.description or "",
                "status": booking.status.value if hasattr(booking.status, "value") else booking.status,
                "priority": "medium",  # Default
                "scheduledDate": booking.scheduled_time.date().isoformat(),
                "scheduledTime": booking.scheduled_time.strftime("%H:%M"),
                "price": booking.base_price_cents / 100 if booking.base_price_cents else 0,
            }
        )
    return jobs


from pydantic import BaseModel


class CreateJobRequest(BaseModel):
    customerName: str
    customerPhone: str
    address: str
    serviceType: str
    description: Optional[str] = None
    priority: str
    scheduledDate: date
    scheduledTime: str  # "HH:MM"


@router.post("/jobs")
async def create_job(
    job: CreateJobRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Create a new job (Booking) through the booking repository."""
    tenant_id = current_user.tenant_id

    # 1. Find or Create Customer
    query = select(User).where(User.phone == job.customerPhone, User.tenant_id == tenant_id)
    result = await session.execute(query)
    customer = result.scalar_one_or_none()

    if not customer:
        customer = User(
            id=uuid4(),
            tenant_id=tenant_id,
            email=f"{job.customerPhone}@example.com",  # operator-created stub; real email set via invite
            # Operator-created customer; authenticates via invite/magic link, not this password.
            hashed_password=security_manager.generate_unusable_password_hash(),
            first_name=job.customerName.split(" ")[0],
            last_name=" ".join(job.customerName.split(" ")[1:]) or "Customer",
            phone=job.customerPhone,
            role=UserRole.CUSTOMER,
            is_active=True,
        )
        session.add(customer)
        await session.flush()

    # 2. Find Service
    service_query = select(Service).where(Service.name.ilike(f"%{job.serviceType}%"), Service.tenant_id == tenant_id)
    service_res = await session.execute(service_query)
    service = service_res.scalar_one_or_none()

    if not service:
        provider_res = await session.execute(select(Provider).where(Provider.tenant_id == tenant_id).limit(1))
        provider = provider_res.scalar_one_or_none()
        if not provider:
            raise HTTPException(status_code=404, detail="No provider available to host the service for this job")

        service = Service(
            id=uuid4(),
            tenant_id=tenant_id,
            provider_id=provider.id,
            name=job.serviceType,
            service_type=job.serviceType,
            base_price_cents=10000,
            duration_minutes=60,
        )
        session.add(service)
        await session.flush()

    # 3. Create Booking via repository so conflict checks, audit and tenant scoping apply.
    h, m = map(int, job.scheduledTime.split(":"))
    scheduled_dt = datetime.combine(job.scheduledDate, datetime.min.time(), tzinfo=timezone.utc).replace(hour=h, minute=m)

    set_current_tenant(tenant_id)
    repo = BookingRepository(session)
    booking = await repo.create(
        customer_id=customer.id,
        provider_id=service.provider_id,
        service_id=service.id,
        scheduled_time=scheduled_dt,
        duration_minutes=service.duration_minutes,
        location_postcode="N/A",  # Optional in simplified flow
        base_price_cents=service.base_price_cents,
        description=job.description,
        location_address=job.address,
        payment_timing=PaymentTiming.BEFORE_SERVICE,
        deposit_percentage=0,
    )
    await session.commit()

    return {"id": str(booking.id), "status": "created"}
