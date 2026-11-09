from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ReferralResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    referrer_id: UUID
    referred_id: UUID
    referral_code: str
    reward_cents: int
    is_rewarded: bool
    created_at: datetime


class ReferralStats(BaseModel):
    total_referrals: int
    successful_referrals: int
    total_rewards_cents: int
    referral_code: str
