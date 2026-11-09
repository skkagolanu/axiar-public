"""The single-statement optimization must preserve rollback and version invariants."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.core.database import db_manager
from app.core.exceptions import AppException
from app.core.outbox import OutboxMessage
from app.core.tenant_context import set_current_tenant
from app.domain.audit.models import AuditLog
from app.domain.booking.models import Booking, BookingStatus
from app.domain.booking.repository import BookingRepository


@pytest.fixture
def creation_args(test_customer, test_provider, test_service):
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
async def test_audit_failure_rolls_back_booking_and_outbox(db_session, default_tenant_id, creation_args):
    set_current_tenant(default_tenant_id)
    await db_session.execute(text("ALTER TABLE audit_logs ADD CONSTRAINT test_reject_create CHECK (action <> 'create')"))
    await db_session.commit()
    try:
        with pytest.raises(IntegrityError):
            await BookingRepository(db_session).create(**creation_args)
        await db_session.rollback()
        for model in [Booking, AuditLog, OutboxMessage]:
            assert await db_session.scalar(select(func.count()).select_from(model)) == 0
    finally:
        await db_session.rollback()
        await db_session.execute(text("ALTER TABLE audit_logs DROP CONSTRAINT test_reject_create"))
        await db_session.commit()
        set_current_tenant(None)


@pytest.mark.integration
async def test_stale_update_writes_no_extra_journal(db_session, default_tenant_id, creation_args):
    set_current_tenant(default_tenant_id)
    try:
        booking = await BookingRepository(db_session).create(**creation_args)
        bid = booking.id
        await db_session.commit()
        async with db_manager.session_makers["main"]() as first, db_manager.session_makers["main"]() as second:
            a, b = BookingRepository(first), BookingRepository(second)
            one = await a.get_by_id(bid, with_relationships=False)
            two = await b.get_by_id(bid, with_relationships=False)
            assert one.version == two.version == 1
            await a.update_status(bid, BookingStatus.CONFIRMED, loaded_booking=one)
            await first.commit()
            with pytest.raises(AppException) as error:
                await b.update_status(bid, BookingStatus.CONFIRMED, loaded_booking=two)
            assert error.value.status_code == 409
        assert await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == bid)) == 2
        assert (
            await db_session.scalar(select(func.count()).select_from(OutboxMessage).where(OutboxMessage.aggregate_id == bid))
            == 2
        )
    finally:
        set_current_tenant(None)
