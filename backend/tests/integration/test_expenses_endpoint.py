"""Integration coverage for tenant-scoped expense endpoints."""

import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import security_manager
from app.domain.booking.models import Booking, FieldAgent, Provider, Service
from app.domain.field_ops.models import Expense, ExpenseStatus
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


async def _create_provider_and_agent(db_session, tenant_id, provider_user_id, agent_user_id):
    provider = Provider(tenant_id=tenant_id, user_id=provider_user_id, business_name="Expense Test Co")
    db_session.add(provider)
    await db_session.commit()

    agent = FieldAgent(tenant_id=tenant_id, user_id=agent_user_id, provider_id=provider.id, is_active=True)
    db_session.add(agent)
    await db_session.commit()
    return provider, agent


async def _create_booking(db_session, tenant_id, customer_id, provider_id):
    service = Service(
        tenant_id=tenant_id,
        provider_id=provider_id,
        name="Expense Test Service",
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
async def test_list_expenses_requires_auth(client: AsyncClient):
    r = await client.get("/api/v1/expenses/")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_create_expense_resolves_real_field_agent_id(client: AsyncClient, db_session):
    """The FK regression: field_agent_id must be the FieldAgent row's id, not the User's id."""
    tenant = await _get_default_tenant(db_session)
    provider_user = await _create_user(db_session, "exp_provider1@example.com", UserRole.PROVIDER, tenant.id)
    agent_user = await _create_user(db_session, "exp_agent1@example.com", UserRole.FIELD_AGENT, tenant.id)
    customer = await _create_user(db_session, "exp_customer1@example.com", UserRole.CUSTOMER, tenant.id)
    provider, agent = await _create_provider_and_agent(db_session, tenant.id, provider_user.id, agent_user.id)
    booking = await _create_booking(db_session, tenant.id, customer.id, provider.id)

    headers = await _auth_headers(client, agent_user.email)
    r = await client.post(
        "/api/v1/expenses/",
        json={
            "booking_id": str(booking.id),
            "amount_cents": 2500,
            "category": "fuel",
            "description": "Petrol for site visit",
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["field_agent_id"] == str(agent.id)
    assert data["field_agent_id"] != str(agent_user.id)
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_create_expense_without_field_agent_profile_returns_404(client: AsyncClient, db_session):
    tenant = await _get_default_tenant(db_session)
    provider_user = await _create_user(db_session, "exp_provider2@example.com", UserRole.PROVIDER, tenant.id)
    agent_user = await _create_user(db_session, "exp_agent2@example.com", UserRole.FIELD_AGENT, tenant.id)
    customer = await _create_user(db_session, "exp_customer2@example.com", UserRole.CUSTOMER, tenant.id)
    provider = Provider(tenant_id=tenant.id, user_id=provider_user.id, business_name="Expense Test Co 2")
    db_session.add(provider)
    await db_session.commit()
    booking = await _create_booking(db_session, tenant.id, customer.id, provider.id)

    # No FieldAgent row created for agent_user -- the caller has the right role but no profile.
    headers = await _auth_headers(client, agent_user.email)
    r = await client.post(
        "/api/v1/expenses/",
        json={"booking_id": str(booking.id), "amount_cents": 1000, "category": "parking", "description": "Parking fee"},
        headers=headers,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_my_expenses_filters_to_caller(client: AsyncClient, db_session):
    tenant = await _get_default_tenant(db_session)
    provider_user = await _create_user(db_session, "exp_provider3@example.com", UserRole.PROVIDER, tenant.id)
    agent_user = await _create_user(db_session, "exp_agent3@example.com", UserRole.FIELD_AGENT, tenant.id)
    other_agent_user = await _create_user(db_session, "exp_agent3b@example.com", UserRole.FIELD_AGENT, tenant.id)
    provider, agent = await _create_provider_and_agent(db_session, tenant.id, provider_user.id, agent_user.id)
    _, other_agent = await _create_provider_and_agent(db_session, tenant.id, provider_user.id, other_agent_user.id)
    customer = await _create_user(db_session, "exp_customer3@example.com", UserRole.CUSTOMER, tenant.id)
    booking = await _create_booking(db_session, tenant.id, customer.id, provider.id)

    db_session.add(
        Expense(
            tenant_id=tenant.id,
            booking_id=booking.id,
            field_agent_id=agent.id,
            amount_cents=500,
            category="fuel",
            description="mine",
        )
    )
    db_session.add(
        Expense(
            tenant_id=tenant.id,
            booking_id=booking.id,
            field_agent_id=other_agent.id,
            amount_cents=700,
            category="fuel",
            description="not mine",
        )
    )
    await db_session.commit()

    headers = await _auth_headers(client, agent_user.email)
    r = await client.get("/api/v1/expenses/my-expenses", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["description"] == "mine"


@pytest.mark.asyncio
async def test_approve_expense_updates_status(client: AsyncClient, db_session):
    tenant = await _get_default_tenant(db_session)
    provider_user = await _create_user(db_session, "exp_provider4@example.com", UserRole.PROVIDER, tenant.id)
    agent_user = await _create_user(db_session, "exp_agent4@example.com", UserRole.FIELD_AGENT, tenant.id)
    customer = await _create_user(db_session, "exp_customer4@example.com", UserRole.CUSTOMER, tenant.id)
    provider, agent = await _create_provider_and_agent(db_session, tenant.id, provider_user.id, agent_user.id)
    booking = await _create_booking(db_session, tenant.id, customer.id, provider.id)

    expense = Expense(
        tenant_id=tenant.id,
        booking_id=booking.id,
        field_agent_id=agent.id,
        amount_cents=800,
        category="tools",
        description="Bought a wrench",
    )
    db_session.add(expense)
    await db_session.commit()

    headers = await _auth_headers(client, provider_user.email)
    r = await client.patch(f"/api/v1/expenses/{expense.id}/approve", headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "approved"


@pytest.mark.asyncio
async def test_approve_unknown_expense_returns_404(client: AsyncClient, db_session):
    tenant = await _get_default_tenant(db_session)
    provider_user = await _create_user(db_session, "exp_provider5@example.com", UserRole.PROVIDER, tenant.id)
    headers = await _auth_headers(client, provider_user.email)

    r = await client.patch("/api/v1/expenses/00000000-0000-0000-0000-000000000099/approve", headers=headers)
    assert r.status_code == 404
