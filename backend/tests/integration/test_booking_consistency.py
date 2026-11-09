"""Independent PostgreSQL transactions exercise empty-slot and interval invariants."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, text

from app.core.database import db_manager
from app.core.exceptions import BookingConflictError, NotFoundException
from app.core.tenant_context import set_current_tenant
from app.domain.booking.models import Booking, BookingStatus
from app.domain.booking.repository import BookingRepository


@pytest.fixture
def booking_arguments(default_tenant_id, test_customer, test_provider, test_service):
    return dict(
        customer_id=test_customer,
        provider_id=test_provider,
        service_id=test_service,
        scheduled_time=datetime.now(timezone.utc) + timedelta(days=10),
        duration_minutes=60,
        location_postcode="NG7 2RD",
        base_price_cents=5000,
    )


@pytest.mark.integration
async def test_empty_schedule_concurrent_transactions(db_session, default_tenant_id, booking_arguments):
    barrier = asyncio.Event()
    ready = 0

    async def attempt():
        nonlocal ready
        set_current_tenant(default_tenant_id)
        try:
            async with db_manager.get_session() as session:
                await session.execute(text("SELECT 1"))
                ready += 1
                if ready == 20:
                    barrier.set()
                await barrier.wait()
                await BookingRepository(session).create(**booking_arguments)
            return "created"
        except BookingConflictError:
            return "conflict"
        finally:
            set_current_tenant(None)

    outcomes = await asyncio.wait_for(asyncio.gather(*(attempt() for _ in range(20))), timeout=30)
    assert outcomes.count("created") == 1
    assert outcomes.count("conflict") == 19
    count = await db_session.scalar(
        select(func.count()).select_from(Booking).where(Booking.provider_id == booking_arguments["provider_id"])
    )
    assert count == 1


@pytest.mark.integration
@pytest.mark.parametrize(
    "status",
    [
        BookingStatus.PENDING,
        BookingStatus.CONFIRMED,
        BookingStatus.ASSIGNED,
        BookingStatus.ON_MY_WAY,
        BookingStatus.ARRIVED,
        BookingStatus.DELAYED,
        BookingStatus.IN_PROGRESS,
    ],
)
async def test_occupied_intervals_and_adjacency(db_session, default_tenant_id, booking_arguments, status):
    set_current_tenant(default_tenant_id)
    try:
        booking = Booking(tenant_id=default_tenant_id, **booking_arguments, status=status)
        db_session.add(booking)
        await db_session.commit()
        repo = BookingRepository(db_session)
        start = booking_arguments["scheduled_time"]
        provider = booking_arguments["provider_id"]
        assert not await repo.check_availability(provider, start + timedelta(minutes=30), 60)
        assert not await repo.check_availability(provider, start - timedelta(minutes=30), 60)
        assert not await repo.check_availability(provider, start - timedelta(minutes=30), 120)
        assert await repo.check_availability(provider, start + timedelta(minutes=60), 60)
        assert await repo.check_availability(provider, start - timedelta(minutes=60), 60)
        assert await repo.check_availability(provider, start, 60, exclude_booking_id=booking.id)
    finally:
        set_current_tenant(None)


@pytest.mark.integration
async def test_create_cannot_reference_another_tenants_provider(db_session, default_tenant_id, booking_arguments):
    from uuid import uuid4

    set_current_tenant(uuid4())
    try:
        with pytest.raises(NotFoundException):
            await BookingRepository(db_session).create(**booking_arguments)
    finally:
        set_current_tenant(None)


@pytest.mark.integration
async def test_unrelated_service_cannot_be_attached(db_session, default_tenant_id, booking_arguments):
    from uuid import uuid4

    set_current_tenant(default_tenant_id)
    try:
        with pytest.raises(NotFoundException):
            await BookingRepository(db_session).create(**{**booking_arguments, "service_id": uuid4()})
    finally:
        set_current_tenant(None)
