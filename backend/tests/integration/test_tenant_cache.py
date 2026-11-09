"""Tenant resolution caching: repeat lookups hit no DB SELECT,
and updating/deactivating a tenant invalidates the cache immediately rather
than waiting out the TTL.

Nothing in this test suite initializes the global `cache_manager` singleton
today (its Redis connection is only opened in `main.py`'s lifespan, which
`ASGITransport`-based test clients never trigger) -- these tests connect it
themselves so the caching path is genuinely exercised rather than silently
no-op'ing on every call.
"""

from uuid import uuid4

import pytest

from app.core.cache import cache_manager
from app.core.tenant_middleware import TenantMiddleware
from app.domain.tenant.repository import TenantRepository
from app.domain.tenant.schemas import TenantCreate, TenantUpdate


@pytest.fixture(scope="module", autouse=True)
async def _cache_connected():
    if cache_manager.redis is None:
        await cache_manager.init()
    yield


@pytest.mark.integration
async def test_repeat_resolution_hits_no_db_select(db_session, monkeypatch):
    repo = TenantRepository(db_session)
    tenant = await repo.create(TenantCreate(name="Acme", slug=f"acme-{uuid4().hex[:8]}"))

    call_count = 0
    original_get_by_slug = TenantRepository.get_by_slug

    async def counting_get_by_slug(self, slug):
        nonlocal call_count
        call_count += 1
        return await original_get_by_slug(self, slug)

    monkeypatch.setattr(TenantRepository, "get_by_slug", counting_get_by_slug)

    middleware = TenantMiddleware(app=None)
    first = await middleware._resolve(tenant.slug)
    second = await middleware._resolve(tenant.slug)

    assert call_count == 1  # second lookup was a cache hit, not a DB SELECT
    assert first == second == {"id": str(tenant.id), "is_active": True}


@pytest.mark.integration
async def test_deactivation_invalidates_cache_immediately(db_session):
    repo = TenantRepository(db_session)
    tenant = await repo.create(TenantCreate(name="Acme", slug=f"acme-{uuid4().hex[:8]}"))

    middleware = TenantMiddleware(app=None)
    cached = await middleware._resolve(tenant.slug)
    assert cached["is_active"] is True

    await repo.update(tenant.id, TenantUpdate(is_active=False))

    # Without invalidation this would still read True from cache for up to the TTL.
    resolved_after_update = await middleware._resolve(tenant.slug)
    assert resolved_after_update["is_active"] is False


@pytest.mark.integration
async def test_deactivation_invalidates_cache_by_id_too(db_session):
    """The middleware also caches by UUID (X-Tenant-ID header path) -- invalidation
    must cover that key, not just the slug one."""
    repo = TenantRepository(db_session)
    tenant = await repo.create(TenantCreate(name="Acme", slug=f"acme-{uuid4().hex[:8]}"))

    middleware = TenantMiddleware(app=None)
    cached = await middleware._resolve(str(tenant.id))
    assert cached["is_active"] is True

    await repo.update(tenant.id, TenantUpdate(is_active=False))

    resolved_after_update = await middleware._resolve(str(tenant.id))
    assert resolved_after_update["is_active"] is False
