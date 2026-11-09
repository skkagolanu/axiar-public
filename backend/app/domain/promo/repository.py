from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_context import get_current_tenant
from app.domain.promo.models import PromoCode


class PromoCodeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _apply_tenant_filter(self, query):
        tenant_id = get_current_tenant()
        if tenant_id:
            return query.where(PromoCode.tenant_id == tenant_id)
        return query

    async def create(self, promo_code: PromoCode) -> PromoCode:
        if promo_code.tenant_id is None:
            promo_code.tenant_id = get_current_tenant()
        self.session.add(promo_code)
        await self.session.flush()
        return promo_code

    async def get_by_code(self, code: str) -> PromoCode | None:
        result = await self.session.execute(select(PromoCode).where(PromoCode.code == code.upper()))
        return result.scalar_one_or_none()

    async def validate_and_apply(self, code: str, amount_cents: int) -> tuple[bool, int, str]:
        promo = await self.get_by_code(code)

        if not promo:
            return False, 0, "Invalid promo code"

        if not promo.is_active:
            return False, 0, "Promo code is inactive"

        now = datetime.now(timezone.utc)
        if now < promo.valid_from:
            return False, 0, "Promo code not yet valid"

        if now > promo.valid_until:
            return False, 0, "Promo code expired"

        if promo.max_uses and promo.current_uses >= promo.max_uses:
            return False, 0, "Promo code usage limit reached"

        if amount_cents < promo.min_purchase_cents:
            return False, 0, f"Minimum purchase of £{promo.min_purchase_cents/100:.2f} required"

        if promo.discount_type == "percentage":
            discount = int(amount_cents * promo.discount_value / 100)
        else:
            discount = min(promo.discount_value, amount_cents)

        return True, discount, "Promo code applied successfully"

    async def increment_usage(self, code: str):
        promo = await self.get_by_code(code)
        if promo:
            promo.current_uses += 1
            await self.session.flush()

    async def list_active(self) -> list[PromoCode]:
        query = select(PromoCode).where(PromoCode.is_active == True).order_by(PromoCode.created_at.desc())
        query = self._apply_tenant_filter(query)
        result = await self.session.execute(query)
        return list(result.scalars().all())
