"""Regression test: creating a booking against a REAL existing provider/service must
succeed end to end (the repo's row-locking query must not blow up on Postgres).

Every pre-existing integration test that posts to /api/v1/bookings/ uses random,
non-existent provider/service UUIDs (so the endpoint 404s before reaching
BookingRepository.create()) — none of them exercised check_availability()'s
with_for_update() query against a real Postgres backend. That query eager-loads
Booking's lazy="joined" relationships by default, including the nullable
field_agent relationship, and Postgres rejects FOR UPDATE on the nullable side
of an outer join. This test creates a real provider+service first so the full
path (including the row lock) actually runs.
"""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import security_manager
from app.domain.booking.models import Provider, Service
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
    await db_session.refresh(user)
    return user


async def _create_provider_and_service(db_session, tenant_id, user_id):
    provider = Provider(tenant_id=tenant_id, user_id=user_id, business_name="Lock Regression Provider")
    db_session.add(provider)
    await db_session.commit()
    service = Service(
        tenant_id=tenant_id,
        provider_id=provider.id,
        name="Lock Regression Service",
        service_type="general",
        base_price_cents=5000,
        duration_minutes=60,
    )
    db_session.add(service)
    await db_session.commit()
    await db_session.refresh(provider)
    await db_session.refresh(service)
    return provider, service


async def _login(client: AsyncClient, email: str) -> dict:
    r = await client.post("/api/v1/auth/login", data={"username": email, "password": "Pass123!"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.integration
async def test_create_booking_against_real_provider_succeeds(async_client: AsyncClient, db_session):
    """POST /api/v1/bookings/ with a real provider+service must return 201, not 500."""
    tenant = await _get_default_tenant(db_session)
    provider_owner = await _create_user(db_session, "lock_regression_owner@example.com", UserRole.PROVIDER, tenant.id)
    customer = await _create_user(db_session, "lock_regression_customer@example.com", UserRole.CUSTOMER, tenant.id)
    provider, service = await _create_provider_and_service(db_session, tenant.id, provider_owner.id)

    headers = await _login(async_client, customer.email)
    scheduled_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()

    r = await async_client.post(
        "/api/v1/bookings/",
        json={
            "provider_id": str(provider.id),
            "service_id": str(service.id),
            "scheduled_time": scheduled_time,
            "duration_minutes": 60,
            "location_postcode": "SW1A 1AA",
            "location_address": "10 Downing St",
            "base_price_cents": 5000,
        },
        headers=headers,
    )

    assert r.status_code == 201, r.text
    assert r.json()["status"] == "pending"


@pytest.mark.integration
async def test_second_overlapping_booking_is_rejected(async_client: AsyncClient, db_session):
    """A second booking for the same provider/time must be rejected (409), proving the
    row lock still does its job after the noload("*") fix — it's not just silenced."""
    tenant = await _get_default_tenant(db_session)
    provider_owner = await _create_user(db_session, "lock_regression_owner2@example.com", UserRole.PROVIDER, tenant.id)
    customer_a = await _create_user(db_session, "lock_regression_customer_a@example.com", UserRole.CUSTOMER, tenant.id)
    customer_b = await _create_user(db_session, "lock_regression_customer_b@example.com", UserRole.CUSTOMER, tenant.id)
    provider, service = await _create_provider_and_service(db_session, tenant.id, provider_owner.id)

    scheduled_time = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    booking_payload = {
        "provider_id": str(provider.id),
        "service_id": str(service.id),
        "scheduled_time": scheduled_time,
        "duration_minutes": 60,
        "location_postcode": "SW1A 1AA",
        "location_address": "10 Downing St",
        "base_price_cents": 5000,
    }

    headers_a = await _login(async_client, customer_a.email)
    r1 = await async_client.post("/api/v1/bookings/", json=booking_payload, headers=headers_a)
    assert r1.status_code == 201, r1.text

    headers_b = await _login(async_client, customer_b.email)
    r2 = await async_client.post("/api/v1/bookings/", json=booking_payload, headers=headers_b)
    assert r2.status_code == 409, r2.text


@pytest.mark.integration
async def test_create_booking_nonexistent_service_returns_404(async_client: AsyncClient, db_session):
    """A booking referencing a non-existent service should return 404."""
    tenant = await _get_default_tenant(db_session)
    provider_owner = await _create_user(db_session, "lock_nosvc_owner@example.com", UserRole.PROVIDER, tenant.id)
    customer = await _create_user(db_session, "lock_nosvc_customer@example.com", UserRole.CUSTOMER, tenant.id)
    provider, _ = await _create_provider_and_service(db_session, tenant.id, provider_owner.id)

    headers = await _login(async_client, customer.email)
    scheduled_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()

    r = await async_client.post(
        "/api/v1/bookings/",
        json={
            "provider_id": str(provider.id),
            "service_id": "00000000-0000-0000-0000-00000000dead",
            "scheduled_time": scheduled_time,
            "duration_minutes": 60,
            "location_postcode": "SW1A 1AA",
            "location_address": "10 Downing St",
            "base_price_cents": 5000,
        },
        headers=headers,
    )
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"
