"""Integration tests for booking transitions, dispatch, disputes and tenant settings."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import security_manager
from app.domain.booking.models import Booking, BookingStatus, Provider, Service
from app.domain.tenant.models import Tenant
from app.domain.user.models import User, UserRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_default_tenant(db_session):
    result = await db_session.execute(select(Tenant).where(Tenant.slug == "default"))
    return result.scalar_one()


async def _create_user(db_session, email: str, role: UserRole, tenant_id, **kwargs) -> User:
    user = User(
        tenant_id=tenant_id,
        email=email,
        hashed_password=security_manager.hash_password("Pass123!"),
        first_name=kwargs.pop("first_name", "Test"),
        last_name=kwargs.pop("last_name", "User"),
        role=role,
        is_active=True,
        is_verified=True,
        **kwargs,
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def _login(client: AsyncClient, email: str) -> str:
    r = await client.post("/api/v1/auth/login", data={"username": email, "password": "Pass123!"})
    assert r.status_code == 200
    return r.json()["access_token"]


async def _auth_headers(client: AsyncClient, email: str) -> dict:
    token = await _login(client, email)
    return {"Authorization": f"Bearer {token}"}


async def _create_provider_and_service(db_session, tenant_id, user_id):
    """Create a minimal Provider + Service so Booking FK constraints are satisfied."""
    provider = Provider(tenant_id=tenant_id, user_id=user_id, business_name="Test Provider Co")
    db_session.add(provider)
    await db_session.commit()
    service = Service(
        tenant_id=tenant_id,
        provider_id=provider.id,
        name="Test Service",
        service_type="general",
        base_price_cents=5000,
        duration_minutes=60,
    )
    db_session.add(service)
    await db_session.commit()
    return provider, service


# ---------------------------------------------------------------------------
# B5 — Granular booking status transitions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_status_transition_returns_422(client: AsyncClient, db_session):
    """Attempting a disallowed transition should return 422."""
    import datetime

    tenant = await _get_default_tenant(db_session)
    admin = await _create_user(db_session, "b5_admin@example.com", UserRole.ADMIN, tenant.id)
    provider, service = await _create_provider_and_service(db_session, tenant.id, admin.id)
    headers = await _auth_headers(client, admin.email)

    booking = Booking(
        tenant_id=tenant.id,
        customer_id=admin.id,
        provider_id=provider.id,
        service_id=service.id,
        scheduled_time=datetime.datetime(2026, 12, 1, 10, 0, tzinfo=datetime.timezone.utc),
        location_postcode="SW1A1AA",
        location_address="1 Test St",
        base_price_cents=5000,
        duration_minutes=60,
        status=BookingStatus.PENDING,
    )
    db_session.add(booking)
    await db_session.commit()

    # PENDING → COMPLETED is not allowed
    r = await client.patch(
        f"/api/v1/bookings/{booking.id}/status",
        json={"status": "completed"},
        headers=headers,
    )
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_valid_status_transition_pending_to_confirmed(client: AsyncClient, db_session):
    import datetime

    tenant = await _get_default_tenant(db_session)
    admin = await _create_user(db_session, "b5_admin2@example.com", UserRole.ADMIN, tenant.id)
    provider, service = await _create_provider_and_service(db_session, tenant.id, admin.id)
    headers = await _auth_headers(client, admin.email)

    booking = Booking(
        tenant_id=tenant.id,
        customer_id=admin.id,
        provider_id=provider.id,
        service_id=service.id,
        scheduled_time=datetime.datetime(2026, 12, 1, 10, 0, tzinfo=datetime.timezone.utc),
        location_postcode="SW1A2AA",
        location_address="2 Test St",
        base_price_cents=5000,
        duration_minutes=60,
        status=BookingStatus.PENDING,
    )
    db_session.add(booking)
    await db_session.commit()

    r = await client.patch(
        f"/api/v1/bookings/{booking.id}/status",
        json={"status": "confirmed"},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "confirmed"


# ---------------------------------------------------------------------------
# B6 — Delay endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delay_endpoint_requires_auth(client: AsyncClient):
    r = await client.post("/api/v1/bookings/00000000-0000-0000-0000-000000000001/delay")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_delay_endpoint_not_found(client: AsyncClient, db_session):
    tenant = await _get_default_tenant(db_session)
    admin = await _create_user(db_session, "b6_admin@example.com", UserRole.ADMIN, tenant.id)
    headers = await _auth_headers(client, admin.email)

    r = await client.post(
        "/api/v1/bookings/00000000-0000-0000-0000-000000000099/delay",
        headers=headers,
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# B7 — Dispatch optimize (OR-Tools or fallback)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_optimize_route_returns_result(client: AsyncClient, db_session):
    tenant = await _get_default_tenant(db_session)
    admin = await _create_user(db_session, "b7_admin@example.com", UserRole.ADMIN, tenant.id)
    headers = await _auth_headers(client, admin.email)

    stops = [
        {"id": "a", "lat": 51.5, "lng": -0.1},
        {"id": "b", "lat": 51.51, "lng": -0.12},
        {"id": "c", "lat": 51.49, "lng": -0.09},
    ]
    r = await client.post("/api/v1/dispatch/optimize", json={"stops": stops}, headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert "optimized_order" in data
    assert isinstance(data["optimized_order"], list)


# ---------------------------------------------------------------------------
# B8 — Disputes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disputes_requires_auth(client: AsyncClient):
    r = await client.get("/api/v1/disputes/")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_open_dispute_returns_201(client: AsyncClient, db_session):
    tenant = await _get_default_tenant(db_session)
    customer = await _create_user(db_session, "b8_customer@example.com", UserRole.CUSTOMER, tenant.id)
    headers = await _auth_headers(client, customer.email)

    import datetime

    provider, service = await _create_provider_and_service(db_session, tenant.id, customer.id)

    # Create a booking to dispute
    booking = Booking(
        tenant_id=tenant.id,
        customer_id=customer.id,
        provider_id=provider.id,
        service_id=service.id,
        scheduled_time=datetime.datetime(2026, 12, 2, 10, 0, tzinfo=datetime.timezone.utc),
        location_postcode="SW1A3AA",
        location_address="3 Test St",
        base_price_cents=7500,
        duration_minutes=60,
        status=BookingStatus.COMPLETED,
    )
    db_session.add(booking)
    await db_session.commit()

    r = await client.post(
        "/api/v1/disputes/",
        json={
            "booking_id": str(booking.id),
            "reason": "quality_issue",
            "description": "Work was incomplete.",
        },
        headers=headers,
    )
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "open"
    assert data["reason"] == "quality_issue"


@pytest.mark.asyncio
async def test_list_my_disputes(client: AsyncClient, db_session):
    tenant = await _get_default_tenant(db_session)
    customer = await _create_user(db_session, "b8_customer2@example.com", UserRole.CUSTOMER, tenant.id)
    headers = await _auth_headers(client, customer.email)

    r = await client.get("/api/v1/disputes/my", headers=headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ---------------------------------------------------------------------------
# B9 — System settings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_settings_requires_admin(client: AsyncClient, db_session):
    tenant = await _get_default_tenant(db_session)
    customer = await _create_user(db_session, "b9_customer@example.com", UserRole.CUSTOMER, tenant.id)
    headers = await _auth_headers(client, customer.email)

    r = await client.get("/api/v1/settings/", headers=headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_settings_list_returns_defaults(client: AsyncClient, db_session):
    tenant = await _get_default_tenant(db_session)
    admin = await _create_user(db_session, "b9_admin@example.com", UserRole.ADMIN, tenant.id)
    headers = await _auth_headers(client, admin.email)

    r = await client.get("/api/v1/settings/", headers=headers)
    assert r.status_code == 200
    keys = {s["key"] for s in r.json()}
    assert "commission_pct" in keys
    assert "currency" in keys


@pytest.mark.asyncio
async def test_settings_upsert_and_get(client: AsyncClient, db_session):
    tenant = await _get_default_tenant(db_session)
    admin = await _create_user(db_session, "b9_admin2@example.com", UserRole.ADMIN, tenant.id)
    headers = await _auth_headers(client, admin.email)

    r = await client.put("/api/v1/settings/commission_pct", json={"value": "8"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["value"] == "8"

    r2 = await client.get("/api/v1/settings/commission_pct", headers=headers)
    assert r2.status_code == 200
    assert r2.json()["value"] == "8"


# ---------------------------------------------------------------------------
# B10 — Admin monitoring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failed_payments_requires_admin(client: AsyncClient, db_session):
    tenant = await _get_default_tenant(db_session)
    customer = await _create_user(db_session, "b10_customer@example.com", UserRole.CUSTOMER, tenant.id)
    headers = await _auth_headers(client, customer.email)

    r = await client.get("/api/v1/admin/payments/failed", headers=headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_provider_status_breakdown(client: AsyncClient, db_session):
    tenant = await _get_default_tenant(db_session)
    admin = await _create_user(db_session, "b10_admin@example.com", UserRole.ADMIN, tenant.id)
    headers = await _auth_headers(client, admin.email)

    r = await client.get("/api/v1/admin/providers/status", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert "providers" in data
    assert "field_agents" in data
    assert "active" in data["providers"]
