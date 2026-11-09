import secrets
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_context import get_current_tenant
from app.domain.referral.models import Referral


class ReferralRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _apply_tenant_filter(self, query):
        tenant_id = get_current_tenant()
        if tenant_id:
            return query.where(Referral.tenant_id == tenant_id)
        return query

    async def create(self, referrer_id: UUID, referred_id: UUID, referral_code: str) -> Referral:
        tenant_id = get_current_tenant()
        referral = Referral(
            referrer_id=referrer_id,
            referred_id=referred_id,
            referral_code=referral_code,
            tenant_id=tenant_id,
        )
        self.session.add(referral)
        await self.session.flush()
        return referral

    async def get_by_code(self, code: str) -> Referral | None:
        result = await self.session.execute(select(Referral).where(Referral.referral_code == code))
        return result.scalar_one_or_none()

    async def get_user_referrals(self, user_id: UUID) -> list[Referral]:
        query = select(Referral).where(Referral.referrer_id == user_id)
        query = self._apply_tenant_filter(query)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_stats(self, user_id: UUID, referral_code: str) -> dict:
        query = select(func.count(Referral.id), func.sum(Referral.reward_cents)).where(Referral.referrer_id == user_id)
        query = self._apply_tenant_filter(query)
        result = await self.session.execute(query)
        total, rewards = result.one()

        rewarded_query = select(func.count(Referral.id)).where(Referral.referrer_id == user_id, Referral.is_rewarded == True)
        rewarded_query = self._apply_tenant_filter(rewarded_query)
        rewarded_result = await self.session.execute(rewarded_query)
        successful = rewarded_result.scalar()

        return {
            "total_referrals": total or 0,
            "successful_referrals": successful or 0,
            "total_rewards_cents": rewards or 0,
            "referral_code": referral_code,
        }

    async def mark_rewarded(self, referral_id: UUID, reward_cents: int):
        query = select(Referral).where(Referral.id == referral_id)
        query = self._apply_tenant_filter(query)
        result = await self.session.execute(query)
        referral = result.scalar_one_or_none()
        if referral:
            referral.is_rewarded = True
            referral.reward_cents = reward_cents
            await self.session.flush()


def generate_referral_code() -> str:
    return secrets.token_urlsafe(6).upper()[:8]
