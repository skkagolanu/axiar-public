"""DEMO_MODE payment simulation (hosted demo).

With ``settings.DEMO_MODE`` on, ``create-intent`` must record a payment without
calling Stripe, and ``demo-confirm`` must replay the webhook success path
(payment COMPLETED, ``booking.total_paid_cents`` credited) — idempotently.
With it off (the default), ``demo-confirm`` must not exist (404).
"""

import datetime
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.core.security import security_manager
from app.domain.booking.models import Booking, BookingStatus, Provider, Service
from app.domain.payment.models import Payment, PaymentStatus
from app.domain.tenant.models import Tenant
from app.domain.user.models import User, UserRole

PASSWORD = "TestPass123"


async def _setup_booking(db_session, suffix: str) -> tuple[User, Booking]:
    tenant = (await db_session.execute(select(Tenant).where(Tenant.slug == "default"))).scalar_one()
    owner = User(
        id=uuid4(),
        tenant_id=tenant.id,
        email=f"demo_pay_owner_{suffix}@example.com",
        hashed_password=security_manager.hash_password(PASSWORD),
        first_name="Owner",
        last_name="User",
        role=UserRole.PROVIDER,
        is_active=True,
    )
    customer = User(
        id=uuid4(),
        tenant_id=tenant.id,
        email=f"demo_pay_cust_{suffix}@example.com",
        hashed_password=security_manager.hash_password(PASSWORD),
        first_name="Customer",
        last_name="User",
        role=UserRole.CUSTOMER,
        is_active=True,
    )
    db_session.add_all([owner, customer])
    await db_session.commit()

    provider = Provider(id=uuid4(), tenant_id=tenant.id, user_id=owner.id, business_name="Demo Pay Co")
    db_session.add(provider)
    await db_session.commit()

    service = Service(
        id=uuid4(),
        tenant_id=tenant.id,
        provider_id=provider.id,
        name="Demo Pay Service",
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
        scheduled_time=datetime.datetime(2027, 4, 1, 10, 0, tzinfo=datetime.timezone.utc),
        location_postcode="SW1A1AA",
        location_address="1 Demo Pay St",
        base_price_cents=5000,
        duration_minutes=60,
        status=BookingStatus.PENDING,
    )
    db_session.add(booking)
    await db_session.commit()
    await db_session.refresh(booking)
    return customer, booking


async def _headers(client: AsyncClient, email: str) -> dict:
    r = await client.post("/api/v1/auth/login", data={"username": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.asyncio
async def test_demo_confirm_is_absent_outside_demo_mode(client: AsyncClient, db_session):
    customer, booking = await _setup_booking(db_session, "off")
    r = await client.post(
        "/api/v1/payments/demo-confirm",
        json={"booking_id": str(booking.id), "payment_id": str(uuid4())},
        headers=await _headers(client, customer.email),
    )
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_demo_payment_flow_credits_booking_once(client: AsyncClient, db_session, monkeypatch):
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    customer, booking = await _setup_booking(db_session, "on")
    headers = await _headers(client, customer.email)

    r = await client.post(
        "/api/v1/payments/create-intent",
        json={"booking_id": str(booking.id), "amount_cents": 5000},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    intent = r.json()
    assert intent["client_secret"] == "demo"  # no Stripe call happened

    for _ in range(2):  # second call must be idempotent (no double credit)
        r = await client.post(
            "/api/v1/payments/demo-confirm",
            json={"booking_id": str(booking.id), "payment_id": intent["payment_id"]},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        assert r.json() == {"status": "succeeded"}

    await db_session.refresh(booking)
    assert booking.total_paid_cents == 5000

    payment = (await db_session.execute(select(Payment).where(Payment.id == intent["payment_id"]))).scalar_one()
    assert payment.status == PaymentStatus.SUCCEEDED
    assert payment.stripe_payment_intent_id.startswith("demo_pi_")
