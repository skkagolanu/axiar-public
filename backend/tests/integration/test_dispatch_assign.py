"""Integration tests for automatic and manual booking assignment."""

import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import security_manager
from app.domain.booking.models import Booking, FieldAgent, Provider, Service
from app.domain.tenant.models import Tenant
from app.domain.user.models import User, UserRole


async def _get_default_tenant(db_session):
    result = await db_session.execute(select(Tenant).where(Tenant.slug == "default"))
    return result.scalar_one()


async def _create_user(db_session, email: str, role: UserRole, tenant_id) -> User:
    user = User(
        tenant_id=tenant_id,
        email=email,
        hashed_password=security_manager.hash_password("Pass123!"),
        first_name="Test",
        last_name="User",
        role=role,
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def _auth_headers(client: AsyncClient, email: str) -> dict:
    r = await client.post("/api/v1/auth/login", data={"username": email, "password": "Pass123!"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _create_booking(db_session, tenant_id, customer_id, provider_id):
    service = Service(
        tenant_id=tenant_id,
        provider_id=provider_id,
        name="Dispatch Test Service",
        service_type="general",
        base_price_cents=5000,
        duration_minutes=60,
    )
    db_session.add(service)
    await db_session.commit()

    booking = Booking(
        tenant_id=tenant_id,
        customer_id=customer_id,
        provider_id=provider_id,
        service_id=service.id,
        scheduled_time=datetime.datetime(2026, 12, 1, 10, 0, tzinfo=datetime.timezone.utc),
        location_postcode="SW1A1AA",
        location_address="1 Test St",
        base_price_cents=5000,
        duration_minutes=60,
    )
    db_session.add(booking)
    await db_session.commit()
    return booking


@pytest.mark.asyncio
async def test_manual_assign_requires_auth(client: AsyncClient):
    r = await client.post("/api/v1/dispatch/00000000-0000-0000-0000-000000000001/assign/00000000-0000-0000-0000-000000000002")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_manual_assign_unknown_booking_returns_404(client: AsyncClient, db_session):
    tenant = await _get_default_tenant(db_session)
    admin = await _create_user(db_session, "dispatch_admin1@example.com", UserRole.ADMIN, tenant.id)
    headers = await _auth_headers(client, admin.email)

    r = await client.post(
        "/api/v1/dispatch/00000000-0000-0000-0000-000000000099/assign/00000000-0000-0000-0000-000000000002",
        headers=headers,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_manual_assign_denies_non_owning_provider(client: AsyncClient, db_session):
    tenant = await _get_default_tenant(db_session)
    owner_user = await _create_user(db_session, "dispatch_owner@example.com", UserRole.PROVIDER, tenant.id)
    other_provider_user = await _create_user(db_session, "dispatch_other@example.com", UserRole.PROVIDER, tenant.id)
    owner_provider = Provider(tenant_id=tenant.id, user_id=owner_user.id, business_name="Owner Co")
    db_session.add(owner_provider)
    await db_session.commit()
    other_provider = Provider(tenant_id=tenant.id, user_id=other_provider_user.id, business_name="Other Co")
    db_session.add(other_provider)
    await db_session.commit()

    customer = await _create_user(db_session, "dispatch_customer1@example.com", UserRole.CUSTOMER, tenant.id)
    booking = await _create_booking(db_session, tenant.id, customer.id, owner_provider.id)

    agent_user = await _create_user(db_session, "dispatch_agent1@example.com", UserRole.FIELD_AGENT, tenant.id)
    agent = FieldAgent(tenant_id=tenant.id, user_id=agent_user.id, provider_id=owner_provider.id, is_active=True)
    db_session.add(agent)
    await db_session.commit()

    headers = await _auth_headers(client, other_provider_user.email)
    r = await client.post(f"/api/v1/dispatch/{booking.id}/assign/{agent.id}", headers=headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_manual_assign_success(client: AsyncClient, db_session):
    tenant = await _get_default_tenant(db_session)
    provider_user = await _create_user(db_session, "dispatch_provider2@example.com", UserRole.PROVIDER, tenant.id)
    provider = Provider(tenant_id=tenant.id, user_id=provider_user.id, business_name="Assign Test Co")
    db_session.add(provider)
    await db_session.commit()

    customer = await _create_user(db_session, "dispatch_customer2@example.com", UserRole.CUSTOMER, tenant.id)
    booking = await _create_booking(db_session, tenant.id, customer.id, provider.id)

    agent_user = await _create_user(db_session, "dispatch_agent2@example.com", UserRole.FIELD_AGENT, tenant.id)
    agent = FieldAgent(tenant_id=tenant.id, user_id=agent_user.id, provider_id=provider.id, is_active=True)
    db_session.add(agent)
    await db_session.commit()

    headers = await _auth_headers(client, provider_user.email)
    r = await client.post(f"/api/v1/dispatch/{booking.id}/assign/{agent.id}", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["field_agent_id"] == str(agent.id)
    assert data["status"] == "assigned"


@pytest.mark.asyncio
async def test_auto_assign_no_available_agents_returns_404(client: AsyncClient, db_session):
    """Exercises DispatchRepository.find_available_agents end to end (the code path
    that was broken by the missing `await` on _apply_tenant_filter) via a booking
    with no field agents in range -- must 404 cleanly, not crash."""
    tenant = await _get_default_tenant(db_session)
    provider_user = await _create_user(db_session, "dispatch_provider3@example.com", UserRole.PROVIDER, tenant.id)
    provider = Provider(tenant_id=tenant.id, user_id=provider_user.id, business_name="No Agents Co")
    db_session.add(provider)
    await db_session.commit()

    customer = await _create_user(db_session, "dispatch_customer3@example.com", UserRole.CUSTOMER, tenant.id)
    booking = await _create_booking(db_session, tenant.id, customer.id, provider.id)

    headers = await _auth_headers(client, provider_user.email)
    r = await client.post(f"/api/v1/dispatch/{booking.id}/auto-assign", headers=headers)
    assert r.status_code == 404
    assert "No available agents" in r.json()["detail"]


@pytest.mark.asyncio
async def test_auto_assign_rejects_already_assigned_booking(client: AsyncClient, db_session):
    tenant = await _get_default_tenant(db_session)
    provider_user = await _create_user(db_session, "dispatch_provider4@example.com", UserRole.PROVIDER, tenant.id)
    provider = Provider(tenant_id=tenant.id, user_id=provider_user.id, business_name="Already Assigned Co")
    db_session.add(provider)
    await db_session.commit()

    customer = await _create_user(db_session, "dispatch_customer4@example.com", UserRole.CUSTOMER, tenant.id)
    booking = await _create_booking(db_session, tenant.id, customer.id, provider.id)

    agent_user = await _create_user(db_session, "dispatch_agent4@example.com", UserRole.FIELD_AGENT, tenant.id)
    agent = FieldAgent(tenant_id=tenant.id, user_id=agent_user.id, provider_id=provider.id, is_active=True)
    db_session.add(agent)
    await db_session.commit()

    booking.field_agent_id = agent.id
    await db_session.commit()

    headers = await _auth_headers(client, provider_user.email)
    r = await client.post(f"/api/v1/dispatch/{booking.id}/auto-assign", headers=headers)
    assert r.status_code == 400
