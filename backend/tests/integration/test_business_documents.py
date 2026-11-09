"""Integration tests for business-document ingestion."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import security_manager
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


# ---------------------------------------------------------------------------
# C2 — POST /api/v1/ai/ingest
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_ingest_returns_503_when_vector_store_unavailable(async_client: AsyncClient, db_session):
    """When ChromaDB is not configured the endpoint returns 503."""
    tenant = await _get_default_tenant(db_session)
    admin = await _create_user(db_session, "c2_admin@example.com", UserRole.ADMIN, tenant.id)
    headers = await _auth_headers(async_client, admin.email)

    payload = {"documents": [{"title": "Test doc", "content": "Some content here."}]}
    r = await async_client.post("/api/v1/ai/ingest", json=payload, headers=headers)

    # In CI ChromaDB is not running — the endpoint should gracefully return 503
    assert r.status_code == 503
    assert "Vector store unavailable" in r.json()["detail"]


@pytest.mark.integration
async def test_ingest_requires_admin_role(async_client: AsyncClient, db_session):
    """Non-admin users should receive 403."""
    tenant = await _get_default_tenant(db_session)
    provider = await _create_user(db_session, "c2_provider@example.com", UserRole.PROVIDER, tenant.id)
    headers = await _auth_headers(async_client, provider.email)

    payload = {"documents": [{"title": "Sneaky doc", "content": "Provider trying to ingest."}]}
    r = await async_client.post("/api/v1/ai/ingest", json=payload, headers=headers)

    assert r.status_code == 403


@pytest.mark.integration
async def test_ingest_requires_authentication(async_client: AsyncClient):
    """Unauthenticated requests should be rejected with 401 or 403."""
    payload = {"documents": [{"title": "No auth", "content": "Should be rejected."}]}
    r = await async_client.post("/api/v1/ai/ingest", json=payload)

    assert r.status_code in (401, 403)


@pytest.mark.integration
async def test_ingest_requires_admin_role_customer(async_client: AsyncClient, db_session):
    """Customer (CUSTOMER role) should also receive 403."""
    tenant = await _get_default_tenant(db_session)
    customer = await _create_user(db_session, "c2_customer@example.com", UserRole.CUSTOMER, tenant.id)
    headers = await _auth_headers(async_client, customer.email)

    payload = {"documents": [{"title": "Customer doc", "content": "Customer trying to ingest."}]}
    r = await async_client.post("/api/v1/ai/ingest", json=payload, headers=headers)

    assert r.status_code == 403


@pytest.mark.integration
async def test_ingest_empty_document_list(async_client: AsyncClient, db_session):
    """An empty documents list should succeed (nothing to ingest)."""
    from unittest.mock import MagicMock

    from app.core.vector_store import vector_store

    tenant = await _get_default_tenant(db_session)
    admin = await _create_user(db_session, "c2_empty_admin@example.com", UserRole.ADMIN, tenant.id)
    headers = await _auth_headers(async_client, admin.email)

    # Mock vector_store to simulate ChromaDB being available
    vector_store.collection = MagicMock()
    vector_store.add_documents = MagicMock()

    r = await async_client.post("/api/v1/ai/ingest", json={"documents": []}, headers=headers)
    assert r.status_code == 200
    assert r.json()["ingested"] == 0


@pytest.mark.integration
async def test_ingest_success_with_mocked_chromadb(async_client: AsyncClient, db_session):
    """When ChromaDB is available (mocked), ingest should return 200 with ingested count."""
    from unittest.mock import MagicMock

    from app.core.vector_store import vector_store

    tenant = await _get_default_tenant(db_session)
    admin = await _create_user(db_session, "c2_success_admin@example.com", UserRole.ADMIN, tenant.id)
    headers = await _auth_headers(async_client, admin.email)

    # Mock vector_store to simulate ChromaDB being available
    vector_store.collection = MagicMock()
    vector_store.add_documents = MagicMock()

    payload = {
        "documents": [
            {"title": "Doc 1", "content": "Content of doc 1."},
            {"title": "Doc 2", "content": "Content of doc 2.", "tags": ["tag1", "tag2"]},
        ]
    }
    r = await async_client.post("/api/v1/ai/ingest", json=payload, headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["ingested"] == 2
    assert data["skipped"] == 0
    assert "Ingested" in data["message"]
