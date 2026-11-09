"""Review repository for data access"""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.review.models import Review


class ReviewRepository:
    """Repository for review data access"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, review_id: UUID) -> Optional[Review]:
        """Get review by ID"""
        query = select(Review).where(Review.id == review_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_provider(self, provider_id: UUID) -> List[Review]:
        """Get all reviews for a provider"""
        query = select(Review).where(Review.provider_id == provider_id).order_by(Review.created_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create(self, review: Review) -> Review:
        """Create new review"""
        self.session.add(review)
        await self.session.flush()
        await self.session.refresh(review)
        return review
