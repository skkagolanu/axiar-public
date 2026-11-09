"""Integration coverage for the mobile dashboard endpoint."""

import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import security_manager
from app.domain.booking.models import Booking, Provider, Service
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


@pytest.mark.asyncio
async def test_mobile_dashboard_requires_auth(client: AsyncClient):
    r = await client.get("/api/v1/mobile/dashboard")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_mobile_dashboard_empty_for_new_customer(client: AsyncClient, db_session):
    tenant = await _get_default_tenant(db_session)
    customer = await _create_user(db_session, "mobile_customer1@example.com", UserRole.CUSTOMER, tenant.id)
    headers = await _auth_headers(client, customer.email)

    r = await client.get("/api/v1/mobile/dashboard", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["upcoming_bookings"] == []
    assert data["active_count"] == 0
    assert data["completed_count"] == 0


@pytest.mark.asyncio
async def test_mobile_dashboard_lists_customer_bookings(client: AsyncClient, db_session):
    tenant = await _get_default_tenant(db_session)
    customer = await _create_user(db_session, "mobile_customer2@example.com", UserRole.CUSTOMER, tenant.id)
    provider_user = await _create_user(db_session, "mobile_provider@example.com", UserRole.PROVIDER, tenant.id)
    provider = Provider(tenant_id=tenant.id, user_id=provider_user.id, business_name="Mobile Test Co")
    db_session.add(provider)
    await db_session.commit()

    service = Service(
        tenant_id=tenant.id,
        provider_id=provider.id,
        name="Mobile Test Service",
        service_type="general",
        base_price_cents=5000,
        duration_minutes=60,
    )
    db_session.add(service)
    await db_session.commit()

    booking = Booking(
        tenant_id=tenant.id,
        customer_id=customer.id,
        provider_id=provider.id,
        service_id=service.id,
        scheduled_time=datetime.datetime(2026, 12, 1, 10, 0, tzinfo=datetime.timezone.utc),
        location_postcode="SW1A1AA",
        location_address="1 Test St",
        base_price_cents=5000,
        duration_minutes=60,
    )
    db_session.add(booking)
    await db_session.commit()

    headers = await _auth_headers(client, customer.email)
    r = await client.get("/api/v1/mobile/dashboard", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["active_count"] == 1
    assert len(data["upcoming_bookings"]) == 1
    assert data["upcoming_bookings"][0]["service_name"] == "Mobile Test Service"
    assert data["upcoming_bookings"][0]["provider_name"] == "Mobile Test Co"
