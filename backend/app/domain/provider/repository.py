from typing import List, Optional
from uuid import UUID

from sqlalchemy import bindparam, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_context import get_current_tenant
from app.domain.booking.models import Provider, Service

_PROVIDER_ID_LOOKUP = select(Provider.id).where(
    Provider.user_id == bindparam("user_id"), Provider.tenant_id == bindparam("tenant_id")
)


class ProviderRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _apply_tenant_filter(self, query):
        """Restrict to the current tenant when a tenant context is set."""
        tenant_id = get_current_tenant()
        if tenant_id:
            return query.where(Provider.tenant_id == tenant_id)
        return query

    async def create(
        self,
        user_id: UUID,
        tenant_id: UUID,
        business_name: str,
        service_radius_km: int,
        description: Optional[str] = None,
        business_phone: Optional[str] = None,
        business_email: Optional[str] = None,
        website_url: Optional[str] = None,
    ) -> Provider:
        provider = Provider(
            user_id=user_id,
            tenant_id=tenant_id,
            business_name=business_name,
            description=description,
            business_phone=business_phone,
            business_email=business_email,
            website_url=website_url,
            service_radius_km=service_radius_km,
        )
        self.session.add(provider)
        await self.session.flush()
        await self.session.refresh(provider)
        return provider

    async def get_by_id(self, provider_id: UUID) -> Optional[Provider]:
        result = await self.session.execute(self._apply_tenant_filter(select(Provider).where(Provider.id == provider_id)))
        return result.scalar_one_or_none()

    async def get_by_user_id(self, user_id: UUID) -> Optional[Provider]:
        result = await self.session.execute(self._apply_tenant_filter(select(Provider).where(Provider.user_id == user_id)))
        return result.scalar_one_or_none()

    async def get_id_by_user_id(self, user_id: UUID) -> Optional[UUID]:
        """Resolve authorization ownership without hydrating unrelated profile fields."""
        tenant = get_current_tenant()
        if tenant:
            result = await self.session.execute(_PROVIDER_ID_LOOKUP, {"user_id": user_id, "tenant_id": tenant})
        else:
            result = await self.session.execute(select(Provider.id).where(Provider.user_id == user_id))
        return result.scalar_one_or_none()

    async def list_active(self, limit: int = 50) -> List[Provider]:
        result = await self.session.execute(
            self._apply_tenant_filter(select(Provider).where(Provider.is_active == True)).limit(limit)  # noqa: E712
        )
        return list(result.scalars().all())

    async def update(self, provider_id: UUID, **kwargs) -> Optional[Provider]:
        provider = await self.get_by_id(provider_id)
        if not provider:
            return None
        for key, value in kwargs.items():
            if hasattr(provider, key):
                setattr(provider, key, value)
        await self.session.flush()
        await self.session.refresh(provider)
        return provider


class ServiceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _apply_tenant_filter(self, query):
        """Restrict to the current tenant when a tenant context is set."""
        tenant_id = get_current_tenant()
        if tenant_id:
            return query.where(Service.tenant_id == tenant_id)
        return query

    async def create(
        self,
        provider_id: UUID,
        tenant_id: UUID,
        name: str,
        service_type: str,
        base_price_cents: int,
        duration_minutes: int,
        description: Optional[str] = None,
    ) -> Service:
        service = Service(
            provider_id=provider_id,
            tenant_id=tenant_id,
            name=name,
            description=description,
            service_type=service_type,
            base_price_cents=base_price_cents,
            duration_minutes=duration_minutes,
        )
        self.session.add(service)
        await self.session.flush()
        await self.session.refresh(service)
        return service

    async def get_by_id(self, service_id: UUID) -> Optional[Service]:
        result = await self.session.execute(self._apply_tenant_filter(select(Service).where(Service.id == service_id)))
        return result.scalar_one_or_none()

    async def list_by_provider(self, provider_id: UUID) -> List[Service]:
        result = await self.session.execute(
            self._apply_tenant_filter(select(Service).where(Service.provider_id == provider_id)).order_by(Service.name)
        )
        return list(result.scalars().all())

    async def update(self, service_id: UUID, **kwargs) -> Optional[Service]:
        service = await self.get_by_id(service_id)
        if not service:
            return None
        for key, value in kwargs.items():
            if hasattr(service, key):
                setattr(service, key, value)
        await self.session.flush()
        await self.session.refresh(service)
        return service

    async def delete(self, service_id: UUID) -> bool:
        service = await self.get_by_id(service_id)
        if not service:
            return False
        await self.session.delete(service)
        return True
