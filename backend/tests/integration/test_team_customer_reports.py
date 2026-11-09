"""Integration tests for team, customer and reporting endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import security_manager
from app.domain.booking.models import FieldAgent
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


async def _login(client: AsyncClient, email: str) -> str:
    r = await client.post("/api/v1/auth/login", data={"username": email, "password": "Pass123!"})
    assert r.status_code == 200
    return r.json()["access_token"]


# ---------------------------------------------------------------------------
# Team
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_team_requires_auth(client: AsyncClient):
    r = await client.get("/api/v1/team")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_list_team_empty(client: AsyncClient, db_session):
    tenant = await _get_default_tenant(db_session)
    await _create_user(db_session, "fixture-72d8ee292a2b@example.test", UserRole.ADMIN, tenant.id)
    token = await _login(client, "fixture-72d8ee292a2b@example.test")

    r = await client.get("/api/v1/team", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_team_with_agents(client: AsyncClient, db_session):
    tenant = await _get_default_tenant(db_session)
    admin = await _create_user(db_session, "fixture-bc00340847b8@example.test", UserRole.ADMIN, tenant.id)
    agent_user = await _create_user(
        db_session, "fixture-0eecda0c28fe@example.test", UserRole.FIELD_AGENT, tenant.id, first_name="Marco", last_name="Polo"
    )

    from uuid import uuid4

    from app.domain.booking.models import Provider

    provider = Provider(
        tenant_id=tenant.id,
        user_id=admin.id,
        business_name="Test Co",
    )
    db_session.add(provider)
    await db_session.commit()

    agent = FieldAgent(
        tenant_id=tenant.id,
        user_id=agent_user.id,
        provider_id=provider.id,
        is_active=True,
    )
    db_session.add(agent)
    await db_session.commit()

    token = await _login(client, "fixture-bc00340847b8@example.test")
    r = await client.get("/api/v1/team", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["fullName"] == "Marco Polo"
    assert data[0]["status"] == "active"
    assert "liveStatus" in data[0]


@pytest.mark.asyncio
async def test_update_agent_location_not_found(client: AsyncClient, db_session):
    tenant = await _get_default_tenant(db_session)
    await _create_user(db_session, "fixture-6059a87e23a9@example.test", UserRole.ADMIN, tenant.id)
    token = await _login(client, "fixture-6059a87e23a9@example.test")

    from uuid import uuid4

    r = await client.patch(
        f"/api/v1/team/{uuid4()}/location",
        headers={"Authorization": f"Bearer {token}"},
        json={"lat": 51.5, "lng": -0.1, "heading": 90, "status": "busy"},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_customers_empty(client: AsyncClient, db_session):
    tenant = await _get_default_tenant(db_session)
    await _create_user(db_session, "fixture-98e3da6861be@example.test", UserRole.ADMIN, tenant.id)
    token = await _login(client, "fixture-98e3da6861be@example.test")

    r = await client.get("/api/v1/customers", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    # May contain customers from other tests; just check the shape
    for item in r.json():
        assert "id" in item
        assert "firstName" in item
        assert "totalSpend" in item


@pytest.mark.asyncio
async def test_create_customer(client: AsyncClient, db_session):
    tenant = await _get_default_tenant(db_session)
    await _create_user(db_session, "fixture-48d7ddf948cb@example.test", UserRole.ADMIN, tenant.id)
    token = await _login(client, "fixture-48d7ddf948cb@example.test")

    r = await client.post(
        "/api/v1/customers",
        headers={"Authorization": f"Bearer {token}"},
        json={"firstName": "Jane", "lastName": "Smith", "email": "jane_phase_a@example.com", "phone": "07700900000"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "created"


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revenue_report_returns_30_days(client: AsyncClient, db_session):
    tenant = await _get_default_tenant(db_session)
    await _create_user(db_session, "fixture-bed4cdd986da@example.test", UserRole.ADMIN, tenant.id)
    token = await _login(client, "fixture-bed4cdd986da@example.test")

    r = await client.get("/api/v1/reports/revenue", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == 31  # 30 days + today
    for point in data:
        assert "date" in point
        assert "amount" in point


@pytest.mark.asyncio
async def test_tech_performance_report(client: AsyncClient, db_session):
    tenant = await _get_default_tenant(db_session)
    await _create_user(db_session, "fixture-931fa78a6282@example.test", UserRole.ADMIN, tenant.id)
    token = await _login(client, "fixture-931fa78a6282@example.test")

    r = await client.get("/api/v1/reports/tech-performance", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    for item in data:
        assert "name" in item
        assert "completed" in item
        assert "delayed" in item


# ---------------------------------------------------------------------------
# A5: Voice returns 501
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_voice_update_returns_501(client: AsyncClient, db_session):
    tenant = await _get_default_tenant(db_session)
    agent_user = await _create_user(db_session, "fixture-b0ca3ad16e2f@example.test", UserRole.FIELD_AGENT, tenant.id)
    token = await _login(client, "fixture-b0ca3ad16e2f@example.test")

    import io
    from uuid import uuid4

    r = await client.post(
        f"/api/v1/voice/{uuid4()}/voice-update",
        headers={"Authorization": f"Bearer {token}"},
        files={"audio": ("test.wav", io.BytesIO(b"fake"), "audio/wav")},
    )
    assert r.status_code == 501
