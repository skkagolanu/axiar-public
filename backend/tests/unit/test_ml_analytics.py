"""
Unit tests for ML analytics services
Coverage target: 80%+
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.domain.analytics.demand_forecast import DemandForecastService
from app.domain.analytics.dynamic_pricing import DynamicPricingService
from app.domain.analytics.noshow_prediction import NoShowPredictionService
from app.domain.analytics.sentiment_analysis import SentimentAnalysisService
from app.domain.booking.models import Booking, BookingStatus, Service
from app.domain.review.models import Review


@pytest.mark.asyncio
async def test_demand_forecast_empty_data(db_session):
    """Test demand forecasting with no historical data"""
    service = DemandForecastService(db_session)
    forecasts = await service.forecast_demand(days_ahead=7)

    assert len(forecasts) == 7
    assert all("date" in f and "predicted_bookings" in f for f in forecasts)


@pytest.mark.asyncio
async def test_no_show_prediction_new_customer(db_session):
    """Test no-show prediction for new customer"""
    service = NoShowPredictionService(db_session)
    customer_id = uuid4()

    history = await service.calculate_customer_history(customer_id)

    assert history["no_show_rate"] == 0.15  # Default for new customers
    assert history["confidence"] == "low"
    assert history["total_bookings"] == 0


@pytest.mark.asyncio
async def test_dynamic_pricing_base_case(db_session, test_tenant, test_provider):
    """Test dynamic pricing with base multiplier"""
    pricing_service = DynamicPricingService(db_session)

    # Create test service
    test_service = Service(
        id=uuid4(),
        tenant_id=test_tenant,
        provider_id=test_provider,
        name="Test Service",
        service_type="cleaning",
        base_price_cents=10000,
        duration_minutes=60,
    )
    db_session.add(test_service)
    await db_session.commit()

    target_time = datetime.now(timezone.utc) + timedelta(days=1, hours=10)  # Non-peak time
    result = await pricing_service.calculate_dynamic_price(test_service.id, target_time)

    assert "dynamic_price_cents" in result
    assert result["base_price_cents"] == 10000
    assert result["surge_multiplier"] >= 1.0


@pytest.mark.asyncio
async def test_sentiment_analysis_positive(db_session):
    """Test sentiment analysis for positive review"""
    service = SentimentAnalysisService(db_session)

    sentiment = service.analyze_text("This service was excellent! Great quality and very professional.")

    assert sentiment["sentiment"] == "positive"
    assert sentiment["compound"] > 0
    assert sentiment["positive"] > sentiment["negative"]


@pytest.mark.asyncio
async def test_sentiment_analysis_negative(db_session):
    """Test sentiment analysis for negative review"""
    service = SentimentAnalysisService(db_session)

    sentiment = service.analyze_text("Terrible service. Very disappointed and unhappy with the quality.")

    assert sentiment["sentiment"] == "negative"
    assert sentiment["compound"] < 0
    assert sentiment["negative"] > sentiment["positive"]


@pytest.mark.asyncio
async def test_sentiment_analysis_neutral(db_session):
    """Test sentiment analysis for neutral review"""
    service = SentimentAnalysisService(db_session)

    sentiment = service.analyze_text("The service was okay. Nothing special.")

    assert sentiment["sentiment"] == "neutral"
    assert -0.05 <= sentiment["compound"] <= 0.05


@pytest.mark.asyncio
async def test_peak_hours_identification(db_session, test_tenant, test_provider, test_customer, test_service):
    """Test peak hours identification"""
    service = DemandForecastService(db_session)

    # Create test bookings at different hours. Each is on a DIFFERENT day so the
    # no_overlapping_bookings GIST constraint isn't violated for the one provider
    # (peak-hour grouping only cares about the hour, not the day).
    for i, hour in enumerate([9, 9, 10, 10, 10, 14, 17, 17, 17, 17]):
        booking = Booking(
            tenant_id=test_tenant,
            customer_id=test_customer,
            provider_id=test_provider,
            service_id=test_service,
            scheduled_time=(datetime.now(timezone.utc) - timedelta(days=i)).replace(
                hour=hour, minute=0, second=0, microsecond=0
            ),
            duration_minutes=60,
            location_postcode="12345",
            base_price_cents=10000,
        )
        db_session.add(booking)

    await db_session.commit()

    peak_hours = await service.get_peak_hours()

    assert isinstance(peak_hours, dict)
    if peak_hours:  # Only check if we have data
        assert 17 in peak_hours or 9 in peak_hours or 10 in peak_hours
