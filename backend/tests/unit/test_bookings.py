"""
Unit tests for booking operations

"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.domain.booking.models import Booking, BookingStatus
from app.domain.booking.repository import BookingRepository


@pytest.mark.asyncio
async def test_create_booking(db_session, test_tenant, test_customer, test_provider, test_service):
    """Test creating a booking"""
    repo = BookingRepository(db_session)

    scheduled_time = datetime.now(timezone.utc) + timedelta(days=1)
    booking = Booking(
        id=uuid4(),
        tenant_id=test_tenant,
        customer_id=test_customer,
        provider_id=test_provider,
        service_id=test_service,
        scheduled_time=scheduled_time,
        duration_minutes=60,
        location_postcode="12345",
        base_price_cents=10000,
        status=BookingStatus.PENDING,
    )

    db_session.add(booking)
    await db_session.commit()
    await db_session.refresh(booking)

    assert booking.id is not None
    assert booking.status == BookingStatus.PENDING
    assert booking.base_price_cents == 10000


@pytest.mark.asyncio
async def test_get_booking_by_id(db_session, test_tenant, test_customer, test_provider, test_service):
    """Test retrieving a booking by ID"""
    booking_id = uuid4()
    booking = Booking(
        id=booking_id,
        tenant_id=test_tenant,
        customer_id=test_customer,
        provider_id=test_provider,
        service_id=test_service,
        scheduled_time=datetime.now(timezone.utc) + timedelta(days=1),
        duration_minutes=60,
        location_postcode="12345",
        base_price_cents=10000,
    )

    db_session.add(booking)
    await db_session.commit()

    repo = BookingRepository(db_session)
    found = await repo.get_by_id(booking_id)

    assert found is not None
    assert found.id == booking_id


@pytest.mark.asyncio
async def test_update_booking_status(db_session, test_tenant, test_customer, test_provider, test_service):
    """Test updating booking status"""
    booking = Booking(
        id=uuid4(),
        tenant_id=test_tenant,
        customer_id=test_customer,
        provider_id=test_provider,
        service_id=test_service,
        scheduled_time=datetime.now(timezone.utc) + timedelta(days=1),
        duration_minutes=60,
        location_postcode="12345",
        base_price_cents=10000,
        status=BookingStatus.PENDING,
    )

    db_session.add(booking)
    await db_session.commit()

    booking.status = BookingStatus.CONFIRMED
    await db_session.commit()
    await db_session.refresh(booking)

    assert booking.status == BookingStatus.CONFIRMED


@pytest.mark.asyncio
async def test_cancel_booking(db_session, test_tenant, test_customer, test_provider, test_service):
    """Test cancelling a booking"""
    booking = Booking(
        id=uuid4(),
        tenant_id=test_tenant,
        customer_id=test_customer,
        provider_id=test_provider,
        service_id=test_service,
        scheduled_time=datetime.now(timezone.utc) + timedelta(days=1),
        duration_minutes=60,
        location_postcode="12345",
        base_price_cents=10000,
        status=BookingStatus.CONFIRMED,
    )

    db_session.add(booking)
    await db_session.commit()

    booking.status = BookingStatus.CANCELLED
    await db_session.commit()
    await db_session.refresh(booking)

    assert booking.status == BookingStatus.CANCELLED


@pytest.mark.asyncio
async def test_get_customer_bookings(db_session, test_tenant, test_customer, test_provider, test_service):
    """Test getting all bookings for a customer"""
    from sqlalchemy import select

    # Create multiple bookings
    for i in range(3):
        booking = Booking(
            id=uuid4(),
            tenant_id=test_tenant,
            customer_id=test_customer,
            provider_id=test_provider,
            service_id=test_service,
            scheduled_time=datetime.now(timezone.utc) + timedelta(days=i + 1),
            duration_minutes=60,
            location_postcode="12345",
            base_price_cents=10000,
        )
        db_session.add(booking)

    await db_session.commit()

    result = await db_session.execute(select(Booking).where(Booking.customer_id == test_customer))
    bookings = result.scalars().all()

    assert len(bookings) == 3


@pytest.mark.asyncio
async def test_get_provider_bookings(db_session, test_tenant, test_customer, test_provider, test_service):
    """Test getting all bookings for a provider"""
    from sqlalchemy import select

    # Create multiple bookings
    for i in range(2):
        booking = Booking(
            id=uuid4(),
            tenant_id=test_tenant,
            customer_id=test_customer,
            provider_id=test_provider,
            service_id=test_service,
            scheduled_time=datetime.now(timezone.utc) + timedelta(days=i + 1),
            duration_minutes=60,
            location_postcode="12345",
            base_price_cents=10000,
        )
        db_session.add(booking)

    await db_session.commit()

    result = await db_session.execute(select(Booking).where(Booking.provider_id == test_provider))
    bookings = result.scalars().all()

    assert len(bookings) == 2


@pytest.mark.asyncio
async def test_booking_with_promo_code(db_session, test_tenant, test_customer, test_provider, test_service):
    """Test creating booking with promo code"""
    booking = Booking(
        id=uuid4(),
        tenant_id=test_tenant,
        customer_id=test_customer,
        provider_id=test_provider,
        service_id=test_service,
        scheduled_time=datetime.now(timezone.utc) + timedelta(days=1),
        duration_minutes=60,
        location_postcode="12345",
        base_price_cents=10000,
        promo_code="SAVE20",
    )

    db_session.add(booking)
    await db_session.commit()
    await db_session.refresh(booking)

    assert booking.promo_code == "SAVE20"
    assert booking.base_price_cents == 10000


@pytest.mark.asyncio
async def test_booking_time_conflict(db_session, test_tenant, test_customer, test_provider, test_service):
    """Test detecting booking time conflicts"""
    from sqlalchemy import and_, select

    scheduled_time = datetime.now(timezone.utc) + timedelta(days=1, hours=10)

    # Create first booking
    booking1 = Booking(
        id=uuid4(),
        tenant_id=test_tenant,
        customer_id=test_customer,
        provider_id=test_provider,
        service_id=test_service,
        scheduled_time=scheduled_time,
        duration_minutes=60,
        location_postcode="12345",
        base_price_cents=10000,
    )
    db_session.add(booking1)
    await db_session.commit()

    # Check for conflicts
    end_time = scheduled_time + timedelta(minutes=60)
    result = await db_session.execute(
        select(Booking).where(
            and_(
                Booking.provider_id == test_provider,
                Booking.scheduled_time < end_time,
                Booking.scheduled_time >= scheduled_time,
                Booking.status != BookingStatus.CANCELLED,
            )
        )
    )
    conflicts = result.scalars().all()

    assert len(conflicts) == 1


@pytest.mark.asyncio
async def test_complete_booking(db_session, test_tenant, test_customer, test_provider, test_service):
    """Test completing a booking"""
    booking = Booking(
        id=uuid4(),
        tenant_id=test_tenant,
        customer_id=test_customer,
        provider_id=test_provider,
        service_id=test_service,
        scheduled_time=datetime.now(timezone.utc) - timedelta(hours=2),
        duration_minutes=60,
        location_postcode="12345",
        base_price_cents=10000,
        status=BookingStatus.IN_PROGRESS,
    )

    db_session.add(booking)
    await db_session.commit()

    booking.status = BookingStatus.COMPLETED
    await db_session.commit()
    await db_session.refresh(booking)

    assert booking.status == BookingStatus.COMPLETED


@pytest.mark.asyncio
async def test_booking_payment_timing(db_session, test_tenant, test_customer, test_provider, test_service):
    """Test booking with different payment timings"""
    booking = Booking(
        id=uuid4(),
        tenant_id=test_tenant,
        customer_id=test_customer,
        provider_id=test_provider,
        service_id=test_service,
        scheduled_time=datetime.now(timezone.utc) + timedelta(days=1),
        duration_minutes=60,
        location_postcode="12345",
        base_price_cents=10000,
        payment_timing="AFTER_SERVICE",
    )

    db_session.add(booking)
    await db_session.commit()
    await db_session.refresh(booking)

    assert booking.payment_timing == "after_service"
    assert booking.base_price_cents == 10000
