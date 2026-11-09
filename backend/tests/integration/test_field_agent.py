"""Tests for field agent endpoints"""

import pytest
from httpx import AsyncClient

from app.core.security import security_manager
from app.domain.user.models import User, UserRole


@pytest.mark.asyncio
async def test_agent_expenses_list(client: AsyncClient, db_session):
    """Test field agent can list their expenses"""
    # FieldAgent.id and User.id are distinct identifiers in authorization checks.
    from sqlalchemy import select

    from app.domain.booking.models import FieldAgent, Provider
    from app.domain.tenant.models import Tenant

    result = await db_session.execute(select(Tenant).where(Tenant.slug == "default"))
    tenant = result.scalar_one()

    provider_user = User(
        tenant_id=tenant.id,
        email="fixture-da49a4ea0867@example.test",
        hashed_password=security_manager.hash_password("Provider123!"),
        first_name="Field",
        last_name="Provider",
        role=UserRole.PROVIDER,
        is_active=True,
        is_verified=True,
    )
    db_session.add(provider_user)
    await db_session.commit()

    provider = Provider(tenant_id=tenant.id, user_id=provider_user.id, business_name="Agent Test Co")
    db_session.add(provider)
    await db_session.commit()

    agent = User(
        tenant_id=tenant.id,
        email="fixture-8a07826d247a@example.test",
        hashed_password=security_manager.hash_password("Agent123!"),
        first_name="Field",
        last_name="Agent",
        role=UserRole.FIELD_AGENT,
        is_active=True,
        is_verified=True,
    )
    db_session.add(agent)
    await db_session.commit()

    field_agent = FieldAgent(tenant_id=tenant.id, user_id=agent.id, provider_id=provider.id, is_active=True)
    db_session.add(field_agent)
    await db_session.commit()

    # Login as agent
    response = await client.post("/api/v1/auth/login", data={"username": "fixture-8a07826d247a@example.test", "password": "Agent123!"})
    assert response.status_code == 200
    token = response.json()["access_token"]

    # List expenses
    response = await client.get("/api/v1/expenses/my-expenses", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_agent_expenses_forbidden_for_customer(client: AsyncClient, db_session):
    """Test customer cannot access agent expenses"""
    # Create customer user
    from sqlalchemy import select

    from app.domain.tenant.models import Tenant

    result = await db_session.execute(select(Tenant).where(Tenant.slug == "default"))
    tenant = result.scalar_one()

    customer = User(
        tenant_id=tenant.id,
        email="fixture-8bb7e1b73d15@example.test",
        hashed_password=security_manager.hash_password("Customer123!"),
        first_name="Customer",
        last_name="User",
        role=UserRole.CUSTOMER,
        is_active=True,
        is_verified=True,
    )
    db_session.add(customer)
    await db_session.commit()

    # Login as customer
    response = await client.post("/api/v1/auth/login", data={"username": "fixture-8bb7e1b73d15@example.test", "password": "Customer123!"})
    assert response.status_code == 200
    token = response.json()["access_token"]

    # Try to list expenses
    response = await client.get("/api/v1/expenses/my-expenses", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
