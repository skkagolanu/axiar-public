import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.tenant.models import Tenant


@pytest.mark.integration
@pytest.mark.asyncio
async def test_user_registration_flow(client: AsyncClient, sample_user):
    """Test complete user registration flow"""
    # Register user
    response = await client.post("/api/v1/auth/register", json=sample_user)
    assert response.status_code == 201

    user_data = response.json()
    assert user_data["email"] == sample_user["email"]
    assert user_data["first_name"] == sample_user["first_name"]
    assert "id" in user_data


@pytest.mark.integration
@pytest.mark.asyncio
async def test_user_login_flow(client: AsyncClient, sample_user):
    """Test user login flow"""
    # First register user
    await client.post("/api/v1/auth/register", json=sample_user)

    # Then login
    login_data = {"username": sample_user["email"], "password": sample_user["password"]}
    response = await client.post("/api/v1/auth/login", data=login_data)
    assert response.status_code == 200

    token_data = response.json()
    assert "access_token" in token_data
    assert "refresh_token" in token_data
    assert token_data["token_type"] == "bearer"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_registration_honors_resolved_tenant(client: AsyncClient, db_session: AsyncSession):
    tenant = Tenant(name="Registration Tenant", slug="registration-tenant", is_active=True)
    db_session.add(tenant)
    await db_session.commit()
    payload = {
        "email": "tenant-registration@example.com",
        "password": "TenantPass123!",
        "first_name": "Tenant",
        "last_name": "User",
        "role": "customer",
    }
    headers = {"X-Tenant-Slug": tenant.slug}

    register_response = await client.post("/api/v1/auth/register", json=payload, headers=headers)
    login_response = await client.post(
        "/api/v1/auth/login",
        data={"username": payload["email"], "password": payload["password"]},
        headers=headers,
    )

    assert register_response.status_code == 201
    assert login_response.status_code == 200


@pytest.mark.integration
@pytest.mark.asyncio
async def test_magic_link_flow(client: AsyncClient):
    """Requesting a magic link succeeds; the token is emailed, not returned (no leak)."""
    response = await client.post("/api/v1/auth/magic-link", json={"email": "test@example.com"})
    assert response.status_code == 200
    # The login token is delivered by email and must NOT be present in the response body.
    assert "magic_link" not in response.json()
