"""Integration tests for B3 — no-account (guest) booking via magic link."""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.domain.booking.models import Provider, Service
from app.domain.tenant.models import Tenant
from app.domain.user.models import User, UserRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_default_tenant(db_session):
    result = await db_session.execute(select(Tenant).where(Tenant.slug == "default"))
    return result.scalar_one()


async def _create_provider_and_service(db_session, tenant_id, user_id):
    provider = Provider(tenant_id=tenant_id, user_id=user_id, business_name="Guest Test Provider")
    db_session.add(provider)
    await db_session.commit()
    service = Service(
        tenant_id=tenant_id,
        provider_id=provider.id,
        name="Guest Test Service",
        service_type="general",
        base_price_cents=5000,
        duration_minutes=60,
    )
    db_session.add(service)
    await db_session.commit()
    return provider, service


# ---------------------------------------------------------------------------
# B3 — POST /api/v1/bookings/guest
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_guest_booking_creates_user_and_booking(async_client: AsyncClient, db_session):
    """A brand-new email should create a User + Booking and return 201."""
    from app.core.security import security_manager

    tenant = await _get_default_tenant(db_session)

    # Need a real Provider/Service to satisfy FK validation
    seed_user = User(
        tenant_id=tenant.id,
        email="b3_seed@example.com",
        hashed_password=security_manager.hash_password("Pass123!"),
        first_name="Seed",
        last_name="User",
        role=UserRole.PROVIDER,
        is_active=True,
        is_verified=True,
    )
    db_session.add(seed_user)
    await db_session.commit()

    provider, service = await _create_provider_and_service(db_session, tenant.id, seed_user.id)

    scheduled_time = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()

    payload = {
        "email": "guest_new@example.com",
        "first_name": "Alice",
        "last_name": "Guest",
        "phone": "+44 7700 900001",
        "booking_data": {
            "provider_id": str(provider.id),
            "service_id": str(service.id),
            "scheduled_time": scheduled_time,
            "duration_minutes": 60,
            "location_postcode": "SW1A 1AA",
            "location_address": "10 Downing St",
            "base_price_cents": 5000,
        },
    }

    r = await async_client.post("/api/v1/bookings/guest", json=payload)
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "pending"

    # User should now exist
    result = await db_session.execute(select(User).where(User.email == "guest_new@example.com"))
    user = result.scalar_one_or_none()
    assert user is not None
    assert user.role == UserRole.CUSTOMER


@pytest.mark.integration
async def test_guest_booking_reuses_existing_user(async_client: AsyncClient, db_session):
    """Posting with an email that already exists should reuse the User, not create a duplicate."""
    from app.core.security import security_manager

    tenant = await _get_default_tenant(db_session)

    existing = User(
        tenant_id=tenant.id,
        email="b3_existing@example.com",
        hashed_password=security_manager.hash_password("Pass123!"),
        first_name="Already",
        last_name="Exists",
        role=UserRole.CUSTOMER,
        is_active=True,
        is_verified=True,
    )
    db_session.add(existing)

    seed_user = User(
        tenant_id=tenant.id,
        email="b3_seed2@example.com",
        hashed_password=security_manager.hash_password("Pass123!"),
        first_name="Seed2",
        last_name="User",
        role=UserRole.PROVIDER,
        is_active=True,
        is_verified=True,
    )
    db_session.add(seed_user)
    await db_session.commit()

    provider, service = await _create_provider_and_service(db_session, tenant.id, seed_user.id)

    scheduled_time = (datetime.now(timezone.utc) + timedelta(days=4)).isoformat()

    payload = {
        "email": "b3_existing@example.com",
        "first_name": "Already",
        "last_name": "Exists",
        "booking_data": {
            "provider_id": str(provider.id),
            "service_id": str(service.id),
            "scheduled_time": scheduled_time,
            "duration_minutes": 60,
            "location_postcode": "EC1A 1BB",
            "location_address": "1 Poultry, London",
            "base_price_cents": 5000,
        },
    }

    r = await async_client.post("/api/v1/bookings/guest", json=payload)
    assert r.status_code == 201

    # Only one user with that email
    result = await db_session.execute(select(User).where(User.email == "b3_existing@example.com"))
    assert len(result.scalars().all()) == 1


@pytest.mark.integration
async def test_guest_booking_invalid_provider_returns_404(async_client: AsyncClient, db_session):
    """A non-existent provider_id should return 404."""
    scheduled_time = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    payload = {
        "email": "b3_404@example.com",
        "first_name": "No",
        "last_name": "Provider",
        "booking_data": {
            "provider_id": "00000000-0000-0000-0000-000000000001",
            "service_id": "00000000-0000-0000-0000-000000000002",
            "scheduled_time": scheduled_time,
            "duration_minutes": 60,
            "location_postcode": "M1 1AD",
            "location_address": "1 Test Street",
            "base_price_cents": 5000,
        },
    }
    r = await async_client.post("/api/v1/bookings/guest", json=payload)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Guest payment-flow — create guest booking, then call create-intent with guest token
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_guest_booking_returns_guest_token(async_client: AsyncClient, db_session):
    """The guest-booking response includes a ``guest_token`` JWT."""
    from app.core.security import security_manager

    tenant = await _get_default_tenant(db_session)

    seed_user = User(
        tenant_id=tenant.id,
        email="b3_token_seed@example.com",
        hashed_password=security_manager.hash_password("Pass123!"),
        first_name="TokenSeed",
        last_name="User",
        role=UserRole.PROVIDER,
        is_active=True,
        is_verified=True,
    )
    db_session.add(seed_user)
    await db_session.commit()

    provider, service = await _create_provider_and_service(db_session, tenant.id, seed_user.id)
    scheduled_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()

    payload = {
        "email": "guest_token_test@example.com",
        "first_name": "Token",
        "last_name": "Test",
        "booking_data": {
            "provider_id": str(provider.id),
            "service_id": str(service.id),
            "scheduled_time": scheduled_time,
            "duration_minutes": 60,
            "location_postcode": "SW1A 1AA",
            "base_price_cents": 3000,
        },
    }

    r = await async_client.post("/api/v1/bookings/guest", json=payload)
    assert r.status_code == 201
    data = r.json()
    assert "guest_token" in data, "Response should include a guest_token"
    assert len(data["guest_token"]) > 0

    # Verify the token is a valid JWT with the expected claims
    from app.core.security import security_manager as sm

    decoded = await sm.verify_token(data["guest_token"])
    assert decoded is not None
    assert decoded.get("type") == "guest"
    assert decoded.get("booking_id") == data["id"]
    assert decoded.get("email") == "guest_token_test@example.com"


@pytest.mark.integration
async def test_guest_payment_intent_flow(async_client: AsyncClient, db_session, monkeypatch):
    """Guest can create a PaymentIntent using the X-Guest-Token from the guest booking."""
    from unittest.mock import MagicMock

    from app.core.security import security_manager

    # Mock Stripe so the test does not need live/test keys.
    mock_intent = MagicMock()
    mock_intent.id = "pi_guest_test_123"
    mock_intent.client_secret = "pi_guest_test_123_secret"
    monkeypatch.setattr(
        "app.domain.payment.service.stripe.PaymentIntent.create",
        lambda *args, **kwargs: mock_intent,
    )

    tenant = await _get_default_tenant(db_session)

    seed_user = User(
        tenant_id=tenant.id,
        email="b3_pay_seed@example.com",
        hashed_password=security_manager.hash_password("Pass123!"),
        first_name="PaySeed",
        last_name="User",
        role=UserRole.PROVIDER,
        is_active=True,
        is_verified=True,
    )
    db_session.add(seed_user)
    await db_session.commit()

    provider, service = await _create_provider_and_service(db_session, tenant.id, seed_user.id)
    scheduled_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()

    # Step 1 — Create guest booking
    booking_payload = {
        "email": "guest_pay_test@example.com",
        "first_name": "Pay",
        "last_name": "Test",
        "booking_data": {
            "provider_id": str(provider.id),
            "service_id": str(service.id),
            "scheduled_time": scheduled_time,
            "duration_minutes": 60,
            "location_postcode": "SW1A 1AA",
            "base_price_cents": 3000,
        },
    }

    r = await async_client.post("/api/v1/bookings/guest", json=booking_payload)
    assert r.status_code == 201
    booking_data = r.json()
    guest_token = booking_data["guest_token"]
    booking_id = booking_data["id"]

    # Step 2 — Create payment intent using the guest token
    intent_payload = {"booking_id": booking_id, "amount_cents": 3000}
    r2 = await async_client.post(
        "/api/v1/payments/create-intent",
        json=intent_payload,
        headers={"X-Guest-Token": guest_token},
    )
    assert r2.status_code == 200, f"Expected 200, got {r2.status_code}: {r2.text}"
    intent_data = r2.json()
    assert "client_secret" in intent_data
    assert "payment_id" in intent_data
    assert intent_data["amount_cents"] == 3000


@pytest.mark.integration
async def test_guest_payment_intent_wrong_booking_rejected(async_client: AsyncClient, db_session):
    """Guest token for booking A cannot be used to pay for booking B."""
    from app.core.security import security_manager

    tenant = await _get_default_tenant(db_session)

    seed_user = User(
        tenant_id=tenant.id,
        email="b3_wrong_seed@example.com",
        hashed_password=security_manager.hash_password("Pass123!"),
        first_name="WrongSeed",
        last_name="User",
        role=UserRole.PROVIDER,
        is_active=True,
        is_verified=True,
    )
    db_session.add(seed_user)
    await db_session.commit()

    provider, service = await _create_provider_and_service(db_session, tenant.id, seed_user.id)
    scheduled_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()

    # Create the booking (which generates the guest token)
    payload = {
        "email": "guest_wrong@example.com",
        "first_name": "Wrong",
        "last_name": "Token",
        "booking_data": {
            "provider_id": str(provider.id),
            "service_id": str(service.id),
            "scheduled_time": scheduled_time,
            "duration_minutes": 60,
            "location_postcode": "SW1A 1AA",
            "base_price_cents": 3000,
        },
    }
    r = await async_client.post("/api/v1/bookings/guest", json=payload)
    assert r.status_code == 201
    guest_token = r.json()["guest_token"]

    # Try using the token with a non-existent booking — should fail
    other_booking_id = "00000000-0000-0000-0000-000000009999"
    r2 = await async_client.post(
        "/api/v1/payments/create-intent",
        json={"booking_id": other_booking_id, "amount_cents": 3000},
        headers={"X-Guest-Token": guest_token},
    )
    assert r2.status_code == 403, f"Expected 403, got {r2.status_code}: {r2.text}"


@pytest.mark.integration
async def test_guest_payment_intent_no_auth_rejected(async_client: AsyncClient, db_session):
    """Calling create-intent without Bearer or X-Guest-Token returns 401."""
    r = await async_client.post(
        "/api/v1/payments/create-intent",
        json={"booking_id": "00000000-0000-0000-0000-00000000aaaa", "amount_cents": 3000},
    )
    assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"


@pytest.mark.integration
async def test_guest_payment_intent_malformed_token_rejected(async_client: AsyncClient, db_session):
    """A garbage X-Guest-Token should return 401."""
    r = await async_client.post(
        "/api/v1/payments/create-intent",
        json={"booking_id": "00000000-0000-0000-0000-00000000bbbb", "amount_cents": 3000},
        headers={"X-Guest-Token": "this-is-not-a-valid-jwt"},
    )
    assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"


@pytest.mark.integration
async def test_guest_payment_intent_expired_token_rejected(async_client: AsyncClient, db_session, monkeypatch):
    """An expired X-Guest-Token (verify_token returns None) should return 401."""
    from app.core.security import security_manager

    async def mock_verify(*args, **kwargs):
        return None

    monkeypatch.setattr(security_manager, "verify_token", mock_verify)
    r = await async_client.post(
        "/api/v1/payments/create-intent",
        json={"booking_id": "00000000-0000-0000-0000-00000000cccc", "amount_cents": 3000},
        headers={"X-Guest-Token": "expired-test-token"},
    )
    assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"


@pytest.mark.integration
async def test_guest_booking_conflict_returns_409(async_client: AsyncClient, db_session):
    """Creating two overlapping guest bookings for the same provider should
    return 409 on the second."""
    from app.core.security import security_manager

    tenant = await _get_default_tenant(db_session)
    seed_user = User(
        tenant_id=tenant.id,
        email="b3_conflict_seed@example.com",
        hashed_password=security_manager.hash_password("Pass123!"),
        first_name="ConflictSeed",
        last_name="User",
        role=UserRole.PROVIDER,
        is_active=True,
        is_verified=True,
    )
    db_session.add(seed_user)
    await db_session.commit()
    provider, service = await _create_provider_and_service(db_session, tenant.id, seed_user.id)
    scheduled_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()

    def make_payload(email: str) -> dict:
        return {
            "email": email,
            "first_name": "Conflict",
            "last_name": "Test",
            "booking_data": {
                "provider_id": str(provider.id),
                "service_id": str(service.id),
                "scheduled_time": scheduled_time,
                "duration_minutes": 60,
                "location_postcode": "SW1A 1AA",
                "base_price_cents": 5000,
            },
        }

    r1 = await async_client.post("/api/v1/bookings/guest", json=make_payload("guest_conflict_1@example.com"))
    assert r1.status_code == 201, f"First booking failed: {r1.text}"

    r2 = await async_client.post("/api/v1/bookings/guest", json=make_payload("guest_conflict_2@example.com"))
    assert r2.status_code == 409, f"Expected 409, got {r2.status_code}: {r2.text}"
