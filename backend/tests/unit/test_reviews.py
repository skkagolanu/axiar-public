"""
Unit tests for review system

"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.domain.booking.models import Booking
from app.domain.review.models import Review


@pytest.fixture
async def test_booking(db_session, test_tenant, test_customer, test_provider, test_service):
    """Create a test booking for reviews"""
    booking = Booking(
        id=uuid4(),
        tenant_id=test_tenant,
        customer_id=test_customer,
        provider_id=test_provider,
        service_id=test_service,
        scheduled_time=datetime.now(timezone.utc) + timedelta(days=1),
        duration_minutes=60,
        location_postcode="12345",
        base_price_cents=10000,
    )
    db_session.add(booking)
    await db_session.commit()
    await db_session.refresh(booking)
    return booking.id


@pytest.mark.asyncio
async def test_create_review(db_session, test_customer, test_provider, test_booking):
    """Test creating a review"""
    review = Review(
        id=uuid4(),
        booking_id=test_booking,
        customer_id=test_customer,
        provider_id=test_provider,
        rating=5,
        comment="Excellent service!",
    )

    db_session.add(review)
    await db_session.commit()
    await db_session.refresh(review)

    assert review.id is not None
    assert review.rating == 5


@pytest.mark.asyncio
async def test_get_provider_reviews(db_session, test_customer, test_provider, test_booking):
    """Test getting all reviews for a provider"""
    from sqlalchemy import select

    for i in range(3):
        review = Review(
            id=uuid4(),
            booking_id=test_booking,
            customer_id=test_customer,
            provider_id=test_provider,
            rating=4,
            comment=f"Review {i}",
        )
        db_session.add(review)

    await db_session.commit()

    result = await db_session.execute(select(Review).where(Review.provider_id == test_provider))
    reviews = result.scalars().all()

    assert len(reviews) == 3


@pytest.mark.asyncio
async def test_calculate_average_rating(db_session, test_customer, test_provider, test_booking):
    """Test calculating average rating"""
    from sqlalchemy import func, select

    ratings = [5, 4, 5, 3, 4]
    for rating in ratings:
        review = Review(
            id=uuid4(),
            booking_id=test_booking,
            customer_id=test_customer,
            provider_id=test_provider,
            rating=rating,
            comment="Test",
        )
        db_session.add(review)

    await db_session.commit()

    result = await db_session.execute(select(func.avg(Review.rating)).where(Review.provider_id == test_provider))
    avg_rating = result.scalar()

    assert float(avg_rating) == sum(ratings) / len(ratings)


@pytest.mark.asyncio
async def test_review_rating_range(db_session, test_customer, test_provider, test_booking):
    """Test review rating"""
    review = Review(
        id=uuid4(),
        booking_id=test_booking,
        customer_id=test_customer,
        provider_id=test_provider,
        rating=5,
        comment="Max rating",
    )

    db_session.add(review)
    await db_session.commit()

    assert 1 <= review.rating <= 5


@pytest.mark.asyncio
async def test_get_customer_reviews(db_session, test_customer, test_provider, test_booking):
    """Test getting all reviews by a customer"""
    from sqlalchemy import select

    for i in range(2):
        review = Review(
            id=uuid4(),
            booking_id=test_booking,
            customer_id=test_customer,
            provider_id=test_provider,
            rating=4,
            comment=f"Review {i}",
        )
        db_session.add(review)

    await db_session.commit()

    result = await db_session.execute(select(Review).where(Review.customer_id == test_customer))
    reviews = result.scalars().all()

    assert len(reviews) == 2
