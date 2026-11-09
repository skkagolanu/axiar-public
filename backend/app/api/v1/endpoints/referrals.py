from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user
from app.core.database import get_db_session
from app.domain.referral.models import Referral
from app.domain.referral.repository import ReferralRepository, generate_referral_code
from app.domain.referral.schemas import ReferralResponse, ReferralStats
from app.domain.user.models import User

router = APIRouter()


@router.get("/my-code")
async def get_my_referral_code(
    current_user: User = Depends(get_current_user),
):
    """Get user's referral code"""
    # Generate code from user ID (deterministic)
    code = f"REF{str(current_user.id)[:8].upper()}"
    return {"referral_code": code}


@router.get("/stats", response_model=ReferralStats)
async def get_referral_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get user's referral statistics"""
    repo = ReferralRepository(db)
    code = f"REF{str(current_user.id)[:8].upper()}"
    stats = await repo.get_stats(current_user.id, code)
    return stats


@router.get("/", response_model=List[ReferralResponse])
async def list_my_referrals(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """List user's referrals"""
    repo = ReferralRepository(db)
    referrals = await repo.get_user_referrals(current_user.id)
    return referrals
