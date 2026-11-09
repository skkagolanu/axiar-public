"""Dynamic pricing uses available field agents and excludes overlapping assignments."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.core.tenant_context import set_current_tenant
from app.domain.analytics.dynamic_pricing import DynamicPricingService
from app.domain.booking.models import BookingStatus, FieldAgent
from app.domain.booking.repository import BookingRepository


async def _add_agent(db_session, tenant_id, provider_id, *, is_active=True, is_available=True):
    from app.core.security import security_manager
    from app.domain.user.models import User, UserRole

    user = User(
        id=uuid4(),
        tenant_id=tenant_id,
        email=f"agent_{uuid4().hex[:8]}@example.test",
        hashed_password=security_manager.hash_password("test123"),
        first_name="Field",
        last_name="Agent",
        role=UserRole.FIELD_AGENT,
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    agent = FieldAgent(
        id=uuid4(),
        tenant_id=tenant_id,
        user_id=user.id,
        provider_id=provider_id,
        is_active=is_active,
        is_available=is_available,
    )
    db_session.add(agent)
    await db_session.commit()
    return agent


@pytest.mark.integration
async def test_supply_reflects_active_available_agent_count(db_session, default_tenant_id, test_provider, test_service):
    service = DynamicPricingService(db_session)
    target_time = datetime.now(timezone.utc) + timedelta(days=1)
    window_start = target_time - timedelta(hours=1)
    window_end = target_time + timedelta(hours=1)

    assert await service._calculate_supply(test_service, window_start, window_end) == 0

    await _add_agent(db_session, default_tenant_id, test_provider)
    await _add_agent(db_session, default_tenant_id, test_provider)
    
    await _add_agent(db_session, default_tenant_id, test_provider, is_active=False)
    await _add_agent(db_session, default_tenant_id, test_provider, is_available=False)

    assert await service._calculate_supply(test_service, window_start, window_end) == 2


@pytest.mark.integration
async def test_supply_excludes_agents_busy_in_the_window(
    db_session, default_tenant_id, test_provider, test_service, test_customer
):
    agent = await _add_agent(db_session, default_tenant_id, test_provider)
    await _add_agent(db_session, default_tenant_id, test_provider)

    target_time = datetime.now(timezone.utc) + timedelta(days=1)

    set_current_tenant(default_tenant_id)
    try:
        repo = BookingRepository(db_session)
        booking = await repo.create(
            customer_id=test_customer,
            provider_id=test_provider,
            service_id=test_service,
            scheduled_time=target_time,
            duration_minutes=60,
            location_postcode="NG7 2RD",
            base_price_cents=5000,
        )
        await db_session.commit()
        await repo.update_status(booking.id, BookingStatus.CONFIRMED)
        booking.field_agent_id = agent.id
        await db_session.commit()
    finally:
        set_current_tenant(None)

    service = DynamicPricingService(db_session)
    window_start = target_time - timedelta(hours=1)
    window_end = target_time + timedelta(hours=1)

    
    assert await service._calculate_supply(test_service, window_start, window_end) == 1
