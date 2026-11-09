from typing import List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_context import get_current_tenant
from app.domain.booking_rules.rules import BookingRule


class BookingRuleRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        provider_id: UUID,
        name: str,
        conditions: dict,
        priority: int = 0,
    ) -> BookingRule:
        """Create booking rule"""
        tenant_id = get_current_tenant()
        if not tenant_id:
            raise ValueError("Tenant context required")

        rule = BookingRule(
            tenant_id=tenant_id,
            provider_id=provider_id,
            name=name,
            conditions=conditions,
            priority=priority,
        )

        self.session.add(rule)
        await self.session.flush()
        return rule

    async def get_by_provider(self, provider_id: UUID) -> List[BookingRule]:
        """Get all active rules for provider"""
        tenant_id = get_current_tenant()
        query = select(BookingRule).where(
            BookingRule.provider_id == provider_id,
            BookingRule.is_active == True,
        )

        if tenant_id:
            query = query.where(BookingRule.tenant_id == tenant_id)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update(self, rule_id: UUID, **kwargs) -> BookingRule:
        """Update rule"""
        tenant_id = get_current_tenant()
        query = select(BookingRule).where(BookingRule.id == rule_id)

        if tenant_id:
            query = query.where(BookingRule.tenant_id == tenant_id)

        result = await self.session.execute(query)
        rule = result.scalar_one_or_none()

        if rule:
            for key, value in kwargs.items():
                if hasattr(rule, key):
                    setattr(rule, key, value)
            await self.session.flush()

        return rule
