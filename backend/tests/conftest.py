"""Shared async API, database and synthetic-user fixtures."""

import asyncio
import os
from typing import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.database import Base, get_db_session
from app.main import app

# Test database URL — honor the env (CI sets DATABASE_URL to the runner's postgres
# service); fall back to the docker-compose service name for local runs.
TEST_DATABASE_URL = (
    os.getenv("TEST_DATABASE_URL")
    or os.getenv("DATABASE_URL")
    or "postgresql+asyncpg://axiar:password@postgres:5432/axiar_test"
)

# Create test engine
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    poolclass=NullPool,
)

TestSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Create all tables and default tenant before tests"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def _setup():
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Create default tenant for integration tests
        async with TestSessionLocal() as session:
            from sqlalchemy import select

            from app.domain.tenant.models import Tenant

            result = await session.execute(select(Tenant).where(Tenant.slug == "default"))
            if not result.scalar_one_or_none():
                default_tenant = Tenant(
                    id=uuid4(),
                    name="Default Tenant",
                    slug="default",
                    is_active=True,
                )
                session.add(default_tenant)
                await session.commit()

    loop.run_until_complete(_setup())
    yield

    async def _teardown():
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await test_engine.dispose()

    loop.run_until_complete(_teardown())
    loop.close()


async def _wipe_data():
    """Delete committed test rows while preserving the default tenant.
    API requests use independent connections, so isolation uses a full data wipe."""
    async with test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            if table.name != "tenants":
                await conn.execute(table.delete())


@pytest.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """A *committing* session, wiped afterward for isolation.

    Test data must be committed (not a savepoint-rollback session) so it is visible
    across connections — in particular to the ASGI app under test, which resolves
    its own session on a separate connection. Otherwise auth/lookup fixtures create
    users the app can't see (401s).
    """
    async with TestSessionLocal() as session:
        yield session
    await _wipe_data()


async def override_get_db():
    """Separate session per request. The ASGI app must NOT share the test's
    db_session connection — Starlette runs the request in its own task, so sharing
    one asyncpg connection across two coroutines raises 'another operation is in
    progress'. This session reads committed fixture data."""
    async with TestSessionLocal() as session:
        yield session


@pytest.fixture(scope="function")
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client for integration tests (separate DB session from the test).

    Integration writes commit on a separate connection, so afterward we wipe the
    data tables (keeping the default tenant) to keep tests isolated — otherwise
    committed rows leak into later tests (e.g. overlapping-booking violations).
    """
    app.dependency_overrides[get_db_session] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        try:
            yield client
        finally:
            app.dependency_overrides.clear()

    await _wipe_data()


@pytest.fixture
async def client(async_client: AsyncClient) -> AsyncClient:
    """Alias for async_client for integration tests"""
    return async_client


@pytest.fixture
async def test_tenant(default_tenant_id):
    """Return the default tenant ID for tests"""
    return default_tenant_id


@pytest.fixture
async def test_provider(db_session: AsyncSession, default_tenant_id):
    """Create a test provider"""
    from app.core.security import security_manager
    from app.domain.booking.models import Provider
    from app.domain.user.models import User, UserRole

    # Create user for provider
    user = User(
        id=uuid4(),
        tenant_id=default_tenant_id,
        email=f"provider_{uuid4().hex[:8]}@example.test",
        hashed_password=security_manager.hash_password("test123"),
        first_name="Test",
        last_name="Provider",
        role=UserRole.PROVIDER,
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    provider = Provider(
        id=uuid4(),
        tenant_id=default_tenant_id,
        user_id=user.id,
        business_name="Test Business",
        is_active=True,
    )
    db_session.add(provider)
    await db_session.commit()
    await db_session.refresh(provider)
    return provider.id


@pytest.fixture
async def test_customer(db_session: AsyncSession, default_tenant_id):
    """Create a test customer"""
    from app.core.security import security_manager
    from app.domain.user.models import User, UserRole

    user = User(
        id=uuid4(),
        tenant_id=default_tenant_id,
        email=f"customer_{uuid4().hex[:8]}@example.test",
        hashed_password=security_manager.hash_password("test123"),
        first_name="Test",
        last_name="Customer",
        role=UserRole.CUSTOMER,
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user.id


@pytest.fixture
async def test_service(db_session: AsyncSession, default_tenant_id, test_provider):
    """Create a test service"""
    from app.domain.booking.models import Service

    service = Service(
        id=uuid4(),
        tenant_id=default_tenant_id,
        provider_id=test_provider,
        name="Test Service",
        service_type="cleaning",
        base_price_cents=10000,
        duration_minutes=60,
    )
    db_session.add(service)
    await db_session.commit()
    await db_session.refresh(service)
    return service.id


@pytest.fixture(scope="session")
async def default_tenant_id():
    """Get the default tenant ID created during setup"""
    async with TestSessionLocal() as session:
        from sqlalchemy import select

        from app.domain.tenant.models import Tenant

        result = await session.execute(select(Tenant).where(Tenant.slug == "default"))
        tenant = result.scalar_one()
        return tenant.id


@pytest.fixture
async def admin_token(db_session: AsyncSession, default_tenant_id) -> str:
    """Create real admin user and return JWT token"""
    from app.core.security import security_manager
    from app.domain.user.models import User, UserRole

    admin = User(
        id=uuid4(),
        tenant_id=default_tenant_id,
        email=f"test_admin_{uuid4().hex[:8]}@example.test",
        hashed_password=security_manager.hash_password("testpass123"),
        first_name="Test",
        last_name="Admin",
        role=UserRole.ADMIN,
        is_active=True,
        is_verified=True,
    )
    db_session.add(admin)
    await db_session.commit()

    token = security_manager.create_access_token({"sub": str(admin.id)})
    return token


@pytest.fixture
async def user_token(db_session: AsyncSession, default_tenant_id) -> str:
    """Create real user and return JWT token"""
    from app.core.security import security_manager
    from app.domain.user.models import User, UserRole

    user = User(
        id=uuid4(),
        tenant_id=default_tenant_id,
        email=f"test_user_{uuid4().hex[:8]}@example.test",
        hashed_password=security_manager.hash_password("testpass123"),
        first_name="Test",
        last_name="User",
        role=UserRole.CUSTOMER,
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()

    token = security_manager.create_access_token({"sub": str(user.id)})
    return token


@pytest.fixture
def sample_user():
    """Sample user data for registration tests"""
    return {
        "email": f"testuser_{uuid4().hex[:8]}@example.com",
        "password": "TestPass123!",
        "first_name": "Test",
        "last_name": "User",
        "phone": "+1234567890",
    }
