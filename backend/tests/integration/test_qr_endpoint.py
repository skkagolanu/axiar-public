"""Integration coverage for QR-code endpoints."""

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


async def _create_booking(db_session, tenant_id, customer_id):
    provider_user = await _create_user(db_session, f"qr_provider_{customer_id}@example.com", UserRole.PROVIDER, tenant_id)
    provider = Provider(tenant_id=tenant_id, user_id=provider_user.id, business_name="QR Test Co")
    db_session.add(provider)
    await db_session.commit()

    service = Service(
        tenant_id=tenant_id,
        provider_id=provider.id,
        name="QR Test Service",
        service_type="general",
        base_price_cents=5000,
        duration_minutes=60,
    )
    db_session.add(service)
    await db_session.commit()

    booking = Booking(
        tenant_id=tenant_id,
        customer_id=customer_id,
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
    return booking


@pytest.mark.asyncio
async def test_qr_requires_auth(client: AsyncClient):
    r = await client.get("/api/v1/qr/00000000-0000-0000-0000-000000000001/qr")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_qr_not_found_for_unknown_booking(client: AsyncClient, db_session):
    tenant = await _get_default_tenant(db_session)
    customer = await _create_user(db_session, "qr_customer1@example.com", UserRole.CUSTOMER, tenant.id)
    headers = await _auth_headers(client, customer.email)

    r = await client.get("/api/v1/qr/00000000-0000-0000-0000-000000000099/qr", headers=headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_qr_denies_non_owning_customer(client: AsyncClient, db_session):
    tenant = await _get_default_tenant(db_session)
    owner = await _create_user(db_session, "qr_owner@example.com", UserRole.CUSTOMER, tenant.id)
    other = await _create_user(db_session, "qr_other@example.com", UserRole.CUSTOMER, tenant.id)
    booking = await _create_booking(db_session, tenant.id, owner.id)
    headers = await _auth_headers(client, other.email)

    r = await client.get(f"/api/v1/qr/{booking.id}/qr", headers=headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_qr_generates_png_for_owning_customer(client: AsyncClient, db_session):
    tenant = await _get_default_tenant(db_session)
    customer = await _create_user(db_session, "qr_customer2@example.com", UserRole.CUSTOMER, tenant.id)
    booking = await _create_booking(db_session, tenant.id, customer.id)
    headers = await _auth_headers(client, customer.email)

    r = await client.get(f"/api/v1/qr/{booking.id}/qr", headers=headers)
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
