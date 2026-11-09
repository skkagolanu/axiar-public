"""BookingStatus.NO_SHOW end-to-end: a real transition through
BookingRepository.update_status, and the predictor counting NO_SHOW directly
instead of the old CANCELLED proxy.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.tenant_context import set_current_tenant
from app.domain.analytics.noshow_prediction import NoShowPredictionService
from app.domain.booking.models import BookingStatus
from app.domain.booking.repository import BookingRepository


async def _create_confirmed_booking(db_session, tenant_id, customer_id, provider_id, service_id, days_ago):
    set_current_tenant(tenant_id)
    try:
        repo = BookingRepository(db_session)
        booking = await repo.create(
            customer_id=customer_id,
            provider_id=provider_id,
            service_id=service_id,
            scheduled_time=datetime.now(timezone.utc) - timedelta(days=days_ago),
            duration_minutes=60,
            location_postcode="NG7 2RD",
            base_price_cents=5000,
        )
        await db_session.commit()
        booking = await repo.update_status(booking.id, BookingStatus.CONFIRMED)
        await db_session.commit()
        return booking
    finally:
        set_current_tenant(None)


@pytest.mark.integration
async def test_confirmed_booking_can_transition_to_no_show(
    db_session, default_tenant_id, test_customer, test_provider, test_service
):
    booking = await _create_confirmed_booking(
        db_session, default_tenant_id, test_customer, test_provider, test_service, days_ago=1
    )

    set_current_tenant(default_tenant_id)
    try:
        repo = BookingRepository(db_session)
        updated = await repo.update_status(booking.id, BookingStatus.NO_SHOW)
        await db_session.commit()
    finally:
        set_current_tenant(None)

    assert updated is not None
    assert updated.status == BookingStatus.NO_SHOW


@pytest.mark.integration
async def test_no_show_prediction_counts_no_show_status_not_cancelled(
    db_session, default_tenant_id, test_customer, test_provider, test_service
):
    """A cancelled-but-not-no-show booking must not inflate the no-show rate."""
    booking = await _create_confirmed_booking(
        db_session, default_tenant_id, test_customer, test_provider, test_service, days_ago=2
    )
    set_current_tenant(default_tenant_id)
    try:
        repo = BookingRepository(db_session)
        await repo.update_status(booking.id, BookingStatus.CANCELLED)
        await db_session.commit()
    finally:
        set_current_tenant(None)

    service = NoShowPredictionService(db_session)
    history = await service.calculate_customer_history(test_customer)

    # One past booking, cancelled (not no-show) -- rate must be 0, not 1.
    assert history["total_bookings"] == 1
    assert history["no_show_rate"] == 0.0
