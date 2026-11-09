"""Integration coverage for booking schedule endpoints."""

import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import security_manager
from app.domain.booking.models import Booking, BookingStatus, FieldAgent, Provider, Service
from app.domain.tenant.models import Tenant
from app.domain.user.models import User, UserRole


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


async def _auth_headers(client: AsyncClient, email: str) -> dict:
    r = await client.post("/api/v1/auth/login", data={"username": email, "password": "Pass123!"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.asyncio
async def test_schedule_requires_auth(client: AsyncClient):
    r = await client.get("/api/v1/schedule")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_schedule_lists_assigned_bookings(client: AsyncClient, db_session):
    tenant = await _get_default_tenant(db_session)
    admin = await _create_user(db_session, "sched_admin1@example.com", UserRole.ADMIN, tenant.id)
    provider_user = await _create_user(db_session, "sched_provider1@example.com", UserRole.PROVIDER, tenant.id)
    provider = Provider(tenant_id=tenant.id, user_id=provider_user.id, business_name="Schedule Test Co")
    db_session.add(provider)
    await db_session.commit()

    agent_user = await _create_user(db_session, "sched_agent1@example.com", UserRole.FIELD_AGENT, tenant.id)
    agent = FieldAgent(tenant_id=tenant.id, user_id=agent_user.id, provider_id=provider.id, is_active=True)
    db_session.add(agent)
    await db_session.commit()

    service = Service(
        tenant_id=tenant.id,
        provider_id=provider.id,
        name="Schedule Test Service",
        service_type="general",
        base_price_cents=5000,
        duration_minutes=60,
    )
    db_session.add(service)
    await db_session.commit()

    booking = Booking(
        tenant_id=tenant.id,
        customer_id=admin.id,
        provider_id=provider.id,
        service_id=service.id,
        field_agent_id=agent.id,
        scheduled_time=datetime.datetime(2026, 12, 1, 10, 0, tzinfo=datetime.timezone.utc),
        location_postcode="SW1A1AA",
        location_address="1 Test St",
        base_price_cents=5000,
        duration_minutes=60,
        status=BookingStatus.ASSIGNED,
    )
    db_session.add(booking)
    await db_session.commit()

    headers = await _auth_headers(client, admin.email)
    r = await client.get("/api/v1/schedule", headers=headers)
    assert r.status_code == 200
    events = r.json()
    assert len(events) == 1
    assert events[0]["resourceId"] == str(agent.id)
    assert events[0]["title"].startswith("Schedule Test Service")


@pytest.mark.asyncio
async def test_jobs_lists_pending_bookings_only(client: AsyncClient, db_session):
    tenant = await _get_default_tenant(db_session)
    admin = await _create_user(db_session, "sched_admin2@example.com", UserRole.ADMIN, tenant.id)
    customer = await _create_user(
        db_session, "sched_customer1@example.com", UserRole.CUSTOMER, tenant.id, phone="+441234567890"
    )
    provider_user = await _create_user(db_session, "sched_provider2@example.com", UserRole.PROVIDER, tenant.id)
    provider = Provider(tenant_id=tenant.id, user_id=provider_user.id, business_name="Jobs Test Co")
    db_session.add(provider)
    await db_session.commit()

    service = Service(
        tenant_id=tenant.id,
        provider_id=provider.id,
        name="Jobs Test Service",
        service_type="general",
        base_price_cents=5000,
        duration_minutes=60,
    )
    db_session.add(service)
    await db_session.commit()

    pending = Booking(
        tenant_id=tenant.id,
        customer_id=customer.id,
        provider_id=provider.id,
        service_id=service.id,
        scheduled_time=datetime.datetime(2026, 12, 1, 10, 0, tzinfo=datetime.timezone.utc),
        location_postcode="SW1A1AA",
        location_address="1 Test St",
        base_price_cents=5000,
        duration_minutes=60,
        status=BookingStatus.PENDING,
    )
    confirmed = Booking(
        tenant_id=tenant.id,
        customer_id=customer.id,
        provider_id=provider.id,
        service_id=service.id,
        scheduled_time=datetime.datetime(2026, 12, 2, 10, 0, tzinfo=datetime.timezone.utc),
        location_postcode="SW1A2AA",
        location_address="2 Test St",
        base_price_cents=5000,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
    )
    db_session.add_all([pending, confirmed])
    await db_session.commit()

    headers = await _auth_headers(client, admin.email)
    r = await client.get("/api/v1/jobs", headers=headers)
    assert r.status_code == 200
    jobs = r.json()
    assert len(jobs) == 1
    assert jobs[0]["id"] == str(pending.id)
    assert jobs[0]["customerName"] == "Test User"


@pytest.mark.asyncio
async def test_create_job_creates_new_customer_and_service(client: AsyncClient, db_session):
    tenant = await _get_default_tenant(db_session)
    admin = await _create_user(db_session, "sched_admin3@example.com", UserRole.ADMIN, tenant.id)
    provider_user = await _create_user(db_session, "sched_provider3@example.com", UserRole.PROVIDER, tenant.id)
    provider = Provider(tenant_id=tenant.id, user_id=provider_user.id, business_name="Create Job Co")
    db_session.add(provider)
    await db_session.commit()

    headers = await _auth_headers(client, admin.email)
    r = await client.post(
        "/api/v1/jobs",
        json={
            "customerName": "Brand New Customer",
            "customerPhone": "+441112223333",
            "address": "42 New Job Ave",
            "serviceType": "Deep Clean",
            "description": "First-time booking",
            "priority": "medium",
            "scheduledDate": "2026-12-15",
            "scheduledTime": "14:30",
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "created"

    result = await db_session.execute(select(User).where(User.phone == "+441112223333"))
    created_customer = result.scalar_one()
    assert created_customer.first_name == "Brand"
