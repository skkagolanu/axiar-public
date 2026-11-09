from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import require_role
from app.core.database import get_db_session
from app.domain.analytics.demand_forecast import DemandForecastService
from app.domain.analytics.dynamic_pricing import DynamicPricingService
from app.domain.analytics.noshow_prediction import NoShowPredictionService
from app.domain.analytics.sentiment_analysis import SentimentAnalysisService
from app.domain.user.models import User, UserRole

router = APIRouter()


@router.get("/forecast/demand")
async def forecast_demand(
    days_ahead: int = Query(30, ge=1, le=365),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db_session),
):
    """Forecast booking demand for next N days (heuristic — 7-day moving average + weekday pattern, not a trained model)."""
    service = DemandForecastService(db)
    return await service.forecast_demand(days_ahead)


@router.get("/forecast/peak-hours")
async def get_peak_hours(
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db_session),
):
    """Get peak booking hours (real hourly booking-count distribution — a deterministic aggregate, not a prediction)."""
    service = DemandForecastService(db)
    return await service.get_peak_hours()


@router.get("/predict/no-show/{booking_id}")
async def predict_no_show(
    booking_id: UUID,
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.PROVIDER])),
    db: AsyncSession = Depends(get_db_session),
):
    """Predict no-show probability for a booking (heuristic — weighted rules over customer history/advance-booking time/time-of-day/day-of-week, not a trained model)."""
    service = NoShowPredictionService(db)
    return await service.predict_no_show(booking_id)


@router.get("/pricing/dynamic/{service_id}")
async def get_dynamic_price(
    service_id: UUID,
    target_time: datetime,
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.PROVIDER])),
    db: AsyncSession = Depends(get_db_session),
):
    """Calculate dynamic price for a service at a specific time using demand and available supply."""
    service = DynamicPricingService(db)
    return await service.calculate_dynamic_price(service_id, target_time)


@router.get("/sentiment/review/{review_id}")
async def analyze_review_sentiment(
    review_id: UUID,
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.PROVIDER])),
    db: AsyncSession = Depends(get_db_session),
):
    """Analyze sentiment of a review (heuristic — hand-rolled ~36-word lexicon, not VADER or a trained model)."""
    service = SentimentAnalysisService(db)
    return await service.analyze_review(review_id)


@router.get("/sentiment/provider/{provider_id}")
async def analyze_provider_sentiment(
    provider_id: UUID,
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.PROVIDER])),
    db: AsyncSession = Depends(get_db_session),
):
    """Analyze overall sentiment for a provider (heuristic — hand-rolled ~36-word lexicon, not VADER or a trained model)."""
    service = SentimentAnalysisService(db)
    return await service.analyze_provider_sentiment(provider_id)
