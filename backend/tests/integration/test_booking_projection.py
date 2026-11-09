"""Projection must preserve the booking API's complete authorized response shape."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.core.tenant_context import set_current_tenant
from app.domain.booking.models import FieldAgent
from app.domain.booking.repository import BookingRepository
from app.domain.booking.schemas import BookingRead, BookingReadEnriched
from app.domain.user.models import User, UserRole


@pytest.mark.integration
async def test_enriched_projection_matches_full_model(
    db_session, default_tenant_id, test_customer, test_provider, test_service
):
    set_current_tenant(default_tenant_id)
    try:
        agent_user = User(
            id=uuid4(),
            tenant_id=default_tenant_id,
            email=f"agent-{uuid4()}@test.invalid",
            first_name="Assigned",
            last_name="Technician",
            role=UserRole.FIELD_AGENT,
            is_active=True,
        )
        db_session.add(agent_user)
        await db_session.flush()
        agent = FieldAgent(id=uuid4(), tenant_id=default_tenant_id, provider_id=test_provider, user_id=agent_user.id)
        db_session.add(agent)
        await db_session.flush()
        repo = BookingRepository(db_session)
        for i in range(2):
            booking = await repo.create(
                customer_id=test_customer,
                provider_id=test_provider,
                service_id=test_service,
                scheduled_time=datetime.now(timezone.utc) + timedelta(days=10 + i),
                duration_minutes=60,
                location_postcode="NG7 2RD",
                base_price_cents=5000,
            )
            if i == 0:
                booking.field_agent_id = agent.id
            assert BookingRead.model_validate(booking).created_at is not None
        await db_session.commit()
        expected = [
            BookingReadEnriched.from_booking(row).model_dump(mode="json") for row in await repo.list(provider_id=test_provider)
        ]
        actual = [
            BookingReadEnriched.model_validate(row).model_dump(mode="json")
            for row in await repo.list_enriched(provider_id=test_provider)
        ]
        assert actual == expected
        assert len(actual) == 2
        assert any(row["assigned_agent_name"] == "Assigned Technician" for row in actual)
        assert await repo.list_enriched(customer_id=uuid4()) == []
        set_current_tenant(uuid4())
        assert await repo.list_enriched(provider_id=test_provider) == []
    finally:
        set_current_tenant(None)
