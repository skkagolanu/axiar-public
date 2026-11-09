from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user
from app.core.database import get_db_session
from app.domain.booking.models import Booking, BookingStatus, Provider
from app.domain.review.models import Review
from app.domain.user.models import User

router = APIRouter()


class ReviewCreate(BaseModel):
    booking_id: UUID
    rating: int = Field(..., ge=1, le=5)
    comment: str = Field(..., max_length=1000)


class ReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    booking_id: UUID
    customer_id: UUID
    provider_id: UUID
    rating: int
    comment: str


@router.get("/", response_model=List[ReviewResponse])
async def list_reviews(
    skip: int = Query(0, ge=0, le=1_000_000),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """List all reviews for the caller's tenant"""
    result = await db.execute(
        select(Review)
        .where(Review.tenant_id == current_user.tenant_id)
        .offset(skip)
        .limit(limit)
        .order_by(Review.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
async def create_review(
    review_data: ReviewCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Create review for completed booking"""
    result = await db.execute(select(Booking).where(Booking.id == review_data.booking_id))
    booking = result.scalar_one_or_none()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.customer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    if booking.status != BookingStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Can only review completed bookings")

    existing = await db.execute(select(Review).where(Review.booking_id == review_data.booking_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Review already exists")

    review = Review(
        tenant_id=current_user.tenant_id,
        booking_id=review_data.booking_id,
        customer_id=current_user.id,
        provider_id=booking.provider_id,
        rating=review_data.rating,
        comment=review_data.comment,
    )
    db.add(review)

    result = await db.execute(select(Provider).where(Provider.id == booking.provider_id))
    provider = result.scalar_one_or_none()
    if provider:
        avg_result = await db.execute(select(func.avg(Review.rating)).where(Review.provider_id == provider.id))
        provider.average_rating = float(avg_result.scalar() or 0)
        provider.total_reviews += 1

    await db.commit()
    await db.refresh(review)
    return review


@router.get("/provider/{provider_id}", response_model=List[ReviewResponse])
async def get_provider_reviews(
    provider_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get all reviews for a provider (tenant-scoped)"""
    result = await db.execute(
        select(Review)
        .where(Review.provider_id == provider_id, Review.tenant_id == current_user.tenant_id)
        .order_by(Review.created_at.desc())
    )
    return list(result.scalars().all())
