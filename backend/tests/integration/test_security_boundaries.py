"""Authorization and request-boundary regression tests."""

import datetime
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import security_manager
from app.domain.booking.models import Booking, BookingStatus, FieldAgent, Provider, Service
from app.domain.tenant.models import Tenant
from app.domain.user.models import User, UserRole


async def _default_tenant(db_session) -> Tenant:
    return (await db_session.execute(select(Tenant).where(Tenant.slug == "default"))).scalar_one()


async def _user(db_session, email: str, role: UserRole, tenant_id, password: str = "TestPass123") -> User:
    user = User(
        id=uuid4(),
        tenant_id=tenant_id,
        email=email,
        hashed_password=security_manager.hash_password(password),
        first_name="Test",
        last_name="User",
        role=role,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _login(client: AsyncClient, email: str, password: str = "TestPass123") -> dict:
    r = await client.post("/api/v1/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


async def _headers(client: AsyncClient, email: str) -> dict:
    return {"Authorization": f"Bearer {(await _login(client, email))['access_token']}"}


async def _provider_with_service(db_session, tenant_id, user_id):
    provider = Provider(id=uuid4(), tenant_id=tenant_id, user_id=user_id, business_name="Audit Co")
    db_session.add(provider)
    await db_session.commit()
    await db_session.refresh(provider)

    service = Service(
        id=uuid4(),
        tenant_id=tenant_id,
        provider_id=provider.id,
        name="Audit Service",
        service_type="general",
        base_price_cents=5000,
        duration_minutes=60,
    )
    db_session.add(service)
    await db_session.commit()
    return provider, service


async def _booking(db_session, tenant_id, customer_id, provider_id, service_id, **overrides) -> Booking:
    overrides.setdefault("status", BookingStatus.PENDING)
    booking = Booking(
        tenant_id=tenant_id,
        customer_id=customer_id,
        provider_id=provider_id,
        service_id=service_id,
        scheduled_time=datetime.datetime(2027, 3, 1, 10, 0, tzinfo=datetime.timezone.utc),
        location_postcode="SW1A1AA",
        location_address="1 Audit St",
        base_price_cents=5000,
        duration_minutes=60,
        **overrides,
    )
    db_session.add(booking)
    await db_session.commit()
    await db_session.refresh(booking)
    return booking


# ── token type confusion ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_token_is_rejected_as_a_bearer_access_token(client: AsyncClient, db_session):
    """A 7-day refresh token must not authenticate ordinary API calls."""
    tenant = await _default_tenant(db_session)
    await _user(db_session, "s1_refresh@example.com", UserRole.CUSTOMER, tenant.id)
    tokens = await _login(client, "s1_refresh@example.com")

    r = await client.get(
        "/api/v1/bookings/my-bookings",
        headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
    )
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_guest_token_is_rejected_as_a_bearer_access_token(client: AsyncClient, db_session):
    """The booking-scoped guest token must not authenticate as its guest user."""
    tenant = await _default_tenant(db_session)
    guest_token = security_manager.create_access_token(
        data={"sub": f"guest:{uuid4()}"},
        extra_claims={"type": "guest", "booking_id": str(uuid4()), "tenant_id": str(tenant.id)},
    )

    r = await client.get("/api/v1/bookings/my-bookings", headers={"Authorization": f"Bearer {guest_token}"})
    assert r.status_code == 401, r.text


# ── booking listing IDOR ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_customer_listing_bookings_sees_only_their_own(client: AsyncClient, db_session):
    """Booking listings enforce customer ownership within the tenant."""
    tenant = await _default_tenant(db_session)
    owner = await _user(db_session, "s2_owner@example.com", UserRole.PROVIDER, tenant.id)
    provider, service = await _provider_with_service(db_session, tenant.id, owner.id)

    victim = await _user(db_session, "s2_victim@example.com", UserRole.CUSTOMER, tenant.id)
    snooper = await _user(db_session, "s2_snooper@example.com", UserRole.CUSTOMER, tenant.id)

    victim_booking = await _booking(db_session, tenant.id, victim.id, provider.id, service.id)

    r = await client.get("/api/v1/bookings/", headers=await _headers(client, snooper.email))
    assert r.status_code == 200, r.text
    assert [b for b in r.json() if b["id"] == str(victim_booking.id)] == []

    r = await client.get("/api/v1/bookings/", headers=await _headers(client, victim.email))
    assert r.status_code == 200
    assert [b["id"] for b in r.json()] == [str(victim_booking.id)]


@pytest.mark.asyncio
async def test_admin_listing_bookings_sees_the_whole_tenant(client: AsyncClient, db_session):
    tenant = await _default_tenant(db_session)
    owner = await _user(db_session, "s2_admin_owner@example.com", UserRole.PROVIDER, tenant.id)
    provider, service = await _provider_with_service(db_session, tenant.id, owner.id)
    customer = await _user(db_session, "s2_admin_cust@example.com", UserRole.CUSTOMER, tenant.id)
    admin = await _user(db_session, "s2_admin@example.com", UserRole.ADMIN, tenant.id)

    booking = await _booking(db_session, tenant.id, customer.id, provider.id, service.id)

    r = await client.get("/api/v1/bookings/", headers=await _headers(client, admin.email))
    assert r.status_code == 200, r.text
    assert str(booking.id) in [b["id"] for b in r.json()]


@pytest.mark.asyncio
async def test_provider_listing_bookings_sees_their_own_providers_rows(client: AsyncClient, db_session):
    """Provider.id != User.id — the scope must resolve the caller's provider profile."""
    tenant = await _default_tenant(db_session)
    owner = await _user(db_session, "s2_prov@example.com", UserRole.PROVIDER, tenant.id)
    provider, service = await _provider_with_service(db_session, tenant.id, owner.id)
    customer = await _user(db_session, "s2_prov_cust@example.com", UserRole.CUSTOMER, tenant.id)

    booking = await _booking(db_session, tenant.id, customer.id, provider.id, service.id)

    r = await client.get("/api/v1/bookings/", headers=await _headers(client, owner.email))
    assert r.status_code == 200, r.text
    assert [b["id"] for b in r.json()] == [str(booking.id)]


# ── provider identity checks (Provider.id vs User.id) ───────────────────


@pytest.mark.asyncio
async def test_owning_provider_can_advance_their_booking_status(client: AsyncClient, db_session):
    """is_provider compared Provider.id to User.id, so this always 403'd."""
    tenant = await _default_tenant(db_session)
    owner = await _user(db_session, "s3_prov@example.com", UserRole.PROVIDER, tenant.id)
    provider, service = await _provider_with_service(db_session, tenant.id, owner.id)
    customer = await _user(db_session, "s3_cust@example.com", UserRole.CUSTOMER, tenant.id)
    booking = await _booking(db_session, tenant.id, customer.id, provider.id, service.id)

    r = await client.patch(
        f"/api/v1/bookings/{booking.id}/status",
        json={"status": "confirmed"},
        headers=await _headers(client, owner.email),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "confirmed"


@pytest.mark.asyncio
async def test_unrelated_provider_cannot_advance_someone_elses_booking(client: AsyncClient, db_session):
    tenant = await _default_tenant(db_session)
    owner = await _user(db_session, "s3_owner@example.com", UserRole.PROVIDER, tenant.id)
    provider, service = await _provider_with_service(db_session, tenant.id, owner.id)
    customer = await _user(db_session, "s3_other_cust@example.com", UserRole.CUSTOMER, tenant.id)
    booking = await _booking(db_session, tenant.id, customer.id, provider.id, service.id)

    stranger = await _user(db_session, "s3_stranger@example.com", UserRole.PROVIDER, tenant.id)
    await _provider_with_service(db_session, tenant.id, stranger.id)

    r = await client.patch(
        f"/api/v1/bookings/{booking.id}/status",
        json={"status": "confirmed"},
        headers=await _headers(client, stranger.email),
    )
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_unrelated_provider_cannot_report_a_delay(client: AsyncClient, db_session):
    """report_delay allowed *any* provider in the tenant (role check, no ownership check)."""
    tenant = await _default_tenant(db_session)
    owner = await _user(db_session, "s3_delay_owner@example.com", UserRole.PROVIDER, tenant.id)
    provider, service = await _provider_with_service(db_session, tenant.id, owner.id)
    customer = await _user(db_session, "s3_delay_cust@example.com", UserRole.CUSTOMER, tenant.id)
    booking = await _booking(db_session, tenant.id, customer.id, provider.id, service.id, status=BookingStatus.ON_MY_WAY)

    stranger = await _user(db_session, "s3_delay_stranger@example.com", UserRole.PROVIDER, tenant.id)
    await _provider_with_service(db_session, tenant.id, stranger.id)

    r = await client.post(f"/api/v1/bookings/{booking.id}/delay", headers=await _headers(client, stranger.email))
    assert r.status_code == 403, r.text


# ── field-agent GPS spoofing ────────────────────────────────────────────


async def _field_agent(db_session, tenant_id, provider_id, user_id) -> FieldAgent:
    agent = FieldAgent(id=uuid4(), tenant_id=tenant_id, provider_id=provider_id, user_id=user_id, is_active=True, skills=[])
    db_session.add(agent)
    await db_session.commit()
    await db_session.refresh(agent)
    return agent


@pytest.mark.asyncio
async def test_customer_cannot_write_a_field_agents_location(client: AsyncClient, db_session):
    tenant = await _default_tenant(db_session)
    owner = await _user(db_session, "s4_owner@example.com", UserRole.PROVIDER, tenant.id)
    provider, _ = await _provider_with_service(db_session, tenant.id, owner.id)
    agent_user = await _user(db_session, "s4_agent@example.com", UserRole.FIELD_AGENT, tenant.id)
    agent = await _field_agent(db_session, tenant.id, provider.id, agent_user.id)

    customer = await _user(db_session, "s4_cust@example.com", UserRole.CUSTOMER, tenant.id)

    r = await client.patch(
        f"/api/v1/team/{agent.id}/location",
        json={"lat": 51.5, "lng": -0.12, "heading": 0, "status": "busy"},
        headers=await _headers(client, customer.email),
    )
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_agent_can_write_their_own_location(client: AsyncClient, db_session):
    tenant = await _default_tenant(db_session)
    owner = await _user(db_session, "s4_self_owner@example.com", UserRole.PROVIDER, tenant.id)
    provider, _ = await _provider_with_service(db_session, tenant.id, owner.id)
    agent_user = await _user(db_session, "s4_self@example.com", UserRole.FIELD_AGENT, tenant.id)
    agent = await _field_agent(db_session, tenant.id, provider.id, agent_user.id)

    r = await client.patch(
        f"/api/v1/team/{agent.id}/location",
        json={"lat": 51.5, "lng": -0.12, "heading": 0, "status": "busy"},
        headers=await _headers(client, agent_user.email),
    )
    assert r.status_code == 200, r.text


# ── refresh token outlives deactivation ─────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_is_refused_once_the_user_is_deactivated(client: AsyncClient, db_session):
    tenant = await _default_tenant(db_session)
    user = await _user(db_session, "s5_deactivated@example.com", UserRole.CUSTOMER, tenant.id)
    tokens = await _login(client, user.email)

    user.is_active = False
    await db_session.commit()

    r = await client.post("/api/v1/auth/refresh", params={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_access_token_is_refused_at_refresh_endpoint(client: AsyncClient, db_session):
    """The refresh endpoint must not accept an access token in place of a refresh token."""
    tenant = await _default_tenant(db_session)
    await _user(db_session, "s5_wrongtype@example.com", UserRole.CUSTOMER, tenant.id)
    tokens = await _login(client, "s5_wrongtype@example.com")

    r = await client.post("/api/v1/auth/refresh", params={"refresh_token": tokens["access_token"]})
    assert r.status_code == 401, r.text


# ── passwordless accounts and login ─────────────────────────────────────


# ── unauthenticated privilege escalation via /auth/register ───────────


@pytest.mark.asyncio
async def test_public_register_cannot_create_an_admin(client: AsyncClient, db_session):
    """POST /auth/register has no auth dependency at all and took `role` straight from
    the request body — anyone on the internet could self-register as admin."""
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "s14_wannabe_admin@example.com",
            "password": "TestPass123",
            "first_name": "Would",
            "last_name": "BeAdmin",
            "role": "admin",
        },
    )
    assert r.status_code == 403, r.text

    result = await db_session.execute(select(User).where(User.email == "s14_wannabe_admin@example.com"))
    assert result.scalar_one_or_none() is None, "no user row should have been created"


@pytest.mark.asyncio
async def test_public_register_still_allows_provider_self_signup(client: AsyncClient, db_session):
    """The fix must not break the intentional public flow — a business owner
    self-registering as a provider (exercised by the guest-booking E2E happy path)."""
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "s14_real_provider@example.com",
            "password": "TestPass123",
            "first_name": "Real",
            "last_name": "Provider",
            "role": "provider",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "provider"


@pytest.mark.asyncio
async def test_login_against_a_passwordless_account_returns_401_not_500(client: AsyncClient, db_session):
    """Guest/OAuth/magic-link users have hashed_password = NULL. verify_password(None)
    raised, which both 500'd and let a caller enumerate passwordless accounts."""
    tenant = await _default_tenant(db_session)
    user = User(
        id=uuid4(),
        tenant_id=tenant.id,
        email="s6_passwordless@example.com",
        hashed_password=None,
        first_name="Guest",
        last_name="User",
        role=UserRole.CUSTOMER,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    r = await client.post(
        "/api/v1/auth/login",
        data={"username": "s6_passwordless@example.com", "password": "anything"},
    )
    assert r.status_code == 401, r.text
