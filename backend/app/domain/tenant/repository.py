import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_manager
from app.domain.tenant.models import Tenant
from app.domain.tenant.schemas import TenantCreate, TenantUpdate


def _resolve_cache_key(identifier: str) -> str:
    """Mirror TenantMiddleware._resolve's cache key so invalidation targets the same entries."""
    return f"tenant:resolve:{identifier}"


class TenantRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, tenant_data: TenantCreate) -> Tenant:
        tenant = Tenant(**tenant_data.model_dump())
        self.session.add(tenant)
        await self.session.commit()
        await self.session.refresh(tenant)
        return tenant

    async def get_by_id(self, tenant_id: uuid.UUID) -> Tenant | None:
        result = await self.session.execute(select(Tenant).where(Tenant.id == tenant_id))
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Tenant | None:
        result = await self.session.execute(select(Tenant).where(Tenant.slug == slug))
        return result.scalar_one_or_none()

    async def list_all(self, skip: int = 0, limit: int = 100) -> list[Tenant]:
        result = await self.session.execute(select(Tenant).offset(skip).limit(limit))
        return list(result.scalars().all())

    async def update(self, tenant_id: uuid.UUID, tenant_data: TenantUpdate) -> Tenant | None:
        tenant = await self.get_by_id(tenant_id)
        if not tenant:
            return None

        old_slug = tenant.slug

        for field, value in tenant_data.model_dump(exclude_unset=True).items():
            setattr(tenant, field, value)

        await self.session.commit()
        await self.session.refresh(tenant)

        # identifier (UUID or slug) the request used to reach this tenant. Without
        # this, a deactivated tenant (or a changed slug) stays resolvable-as-before
        # for up to the cache's TTL -- invalidate every identifier that could still
        # be pointing at stale data: the tenant's own id, its old slug, and its new
        # slug if it changed.
        await cache_manager.delete(_resolve_cache_key(str(tenant.id)))
        await cache_manager.delete(_resolve_cache_key(old_slug))
        if tenant.slug != old_slug:
            await cache_manager.delete(_resolve_cache_key(tenant.slug))

        return tenant

    async def delete(self, tenant_id: uuid.UUID) -> bool:
        tenant = await self.get_by_id(tenant_id)
        if not tenant:
            return False

        slug = tenant.slug
        await self.session.delete(tenant)
        await self.session.commit()

        await cache_manager.delete(_resolve_cache_key(str(tenant_id)))
        await cache_manager.delete(_resolve_cache_key(slug))

        return True
