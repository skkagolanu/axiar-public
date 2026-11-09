"""Tests for admin endpoints"""

import pytest
from httpx import AsyncClient

from app.core.security import security_manager
from app.domain.user.models import User, UserRole


@pytest.mark.asyncio
async def test_admin_users_list(client: AsyncClient, db_session):
    """Test admin can list users"""
    # Create admin user
    from sqlalchemy import select

    from app.domain.tenant.models import Tenant

    result = await db_session.execute(select(Tenant).where(Tenant.slug == "default"))
    tenant = result.scalar_one()

    admin = User(
        tenant_id=tenant.id,
        email="fixture-e95ebd623fa6@example.test",
        hashed_password=security_manager.hash_password("Admin123!"),
        first_name="Admin",
        last_name="User",
        role=UserRole.ADMIN,
        is_active=True,
        is_verified=True,
    )
    db_session.add(admin)
    await db_session.commit()

    # Login as admin
    response = await client.post("/api/v1/auth/login", data={"username": "fixture-e95ebd623fa6@example.test", "password": "Admin123!"})
    assert response.status_code == 200
    token = response.json()["access_token"]

    # List users
    response = await client.get("/api/v1/admin/users?limit=10", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert "users" in data
    assert "total" in data
    assert isinstance(data["users"], list)


@pytest.mark.asyncio
async def test_admin_users_list_forbidden_for_customer(client: AsyncClient, db_session):
    """Test customer cannot list users"""
    # Create customer user
    from sqlalchemy import select

    from app.domain.tenant.models import Tenant

    result = await db_session.execute(select(Tenant).where(Tenant.slug == "default"))
    tenant = result.scalar_one()

    customer = User(
        tenant_id=tenant.id,
        email="fixture-c5da3c33a03b@example.test",
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
    response = await client.post("/api/v1/auth/login", data={"username": "fixture-c5da3c33a03b@example.test", "password": "Customer123!"})
    assert response.status_code == 200
    token = response.json()["access_token"]

    # Try to list users
    response = await client.get("/api/v1/admin/users?limit=10", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_overview(client: AsyncClient, db_session):
    """Test admin can get system overview"""
    # Create admin user
    from sqlalchemy import select

    from app.domain.tenant.models import Tenant

    result = await db_session.execute(select(Tenant).where(Tenant.slug == "default"))
    tenant = result.scalar_one()

    admin = User(
        tenant_id=tenant.id,
        email="fixture-315a9e0f8e76@example.test",
        hashed_password=security_manager.hash_password("Admin123!"),
        first_name="Admin",
        last_name="User",
        role=UserRole.ADMIN,
        is_active=True,
        is_verified=True,
    )
    db_session.add(admin)
    await db_session.commit()

    # Login as admin
    response = await client.post("/api/v1/auth/login", data={"username": "fixture-315a9e0f8e76@example.test", "password": "Admin123!"})
    assert response.status_code == 200
    token = response.json()["access_token"]

    # Get overview
    response = await client.get("/api/v1/admin/analytics/overview", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
