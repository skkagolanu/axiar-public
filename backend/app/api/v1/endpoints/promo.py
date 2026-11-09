from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user, require_role
from app.core.database import get_db_session
from app.domain.promo.models import PromoCode
from app.domain.promo.repository import PromoCodeRepository
from app.domain.promo.schemas import PromoCodeCreate, PromoCodeResponse, PromoCodeValidation, PromoCodeValidationResponse
from app.domain.user.models import User, UserRole

router = APIRouter()


@router.post("/", response_model=PromoCodeResponse)
async def create_promo_code(
    promo_data: PromoCodeCreate,
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db_session),
):
    """Create promotional code (admin only)"""
    repo = PromoCodeRepository(db)

    # Check if code already exists
    existing = await repo.get_by_code(promo_data.code)
    if existing:
        raise HTTPException(status_code=400, detail="Promo code already exists")

    promo = PromoCode(
        code=promo_data.code.upper(),
        discount_type=promo_data.discount_type,
        discount_value=promo_data.discount_value,
        max_uses=promo_data.max_uses,
        min_purchase_cents=promo_data.min_purchase_cents,
        valid_from=promo_data.valid_from,
        valid_until=promo_data.valid_until,
    )

    await repo.create(promo)
    await db.commit()
    return promo


@router.post("/validate", response_model=PromoCodeValidationResponse)
async def validate_promo_code(
    validation: PromoCodeValidation,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Validate promo code for booking"""
    repo = PromoCodeRepository(db)
    valid, discount, message = await repo.validate_and_apply(validation.code, validation.booking_amount_cents)

    return PromoCodeValidationResponse(valid=valid, discount_cents=discount, message=message)


@router.get("/", response_model=List[PromoCodeResponse])
async def list_promo_codes(
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db_session),
):
    """List all active promo codes (admin only)"""
    repo = PromoCodeRepository(db)
    promos = await repo.list_active()
    return promos
