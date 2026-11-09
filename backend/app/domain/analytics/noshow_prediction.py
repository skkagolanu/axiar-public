"""No-show scoring from customer history, booking lead time and calendar features."""

from datetime import datetime, timedelta, timezone
from typing import Dict
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.booking.models import Booking, BookingStatus


class NoShowPredictionService:
    """Predict likelihood of booking no-shows"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def calculate_customer_history(self, customer_id: UUID) -> Dict:
        """Calculate customer's historical no-show rate"""
        # Get total bookings
        total_result = await self.session.execute(
            select(func.count(Booking.id)).where(
                Booking.customer_id == customer_id, Booking.scheduled_time < datetime.now(timezone.utc)
            )
        )
        total = total_result.scalar() or 0

        # Count explicit NO_SHOW bookings in the customer history.
        no_show_result = await self.session.execute(
            select(func.count(Booking.id)).where(
                Booking.customer_id == customer_id,
                Booking.scheduled_time < datetime.now(timezone.utc),
                Booking.status == BookingStatus.NO_SHOW,
            )
        )
        no_shows = no_show_result.scalar() or 0

        if total == 0:
            return {"no_show_rate": 0.15, "confidence": "low", "total_bookings": 0}

        no_show_rate = no_shows / total
        confidence = "high" if total >= 5 else "medium" if total >= 2 else "low"

        return {"no_show_rate": round(no_show_rate, 2), "confidence": confidence, "total_bookings": total}

    async def predict_no_show(self, booking_id: UUID) -> Dict:
        """
        Predict no-show probability for a booking
        Factors: customer history, advance booking time, time of day, day of week
        """
        result = await self.session.execute(select(Booking).where(Booking.id == booking_id))
        booking = result.scalar_one_or_none()

        if not booking:
            return {"error": "Booking not found"}

        # Customer history (40% weight)
        history = await self.calculate_customer_history(booking.customer_id)
        history_score = history["no_show_rate"] * 0.4

        # Advance booking time (30% weight)
        # Bookings made far in advance have higher no-show rates
        days_ahead = (booking.scheduled_time - booking.created_at).days
        advance_score = min(days_ahead / 30, 1.0) * 0.3  # Max 30 days

        # Time of day (15% weight)
        # Early morning and late evening have higher no-show rates
        hour = booking.scheduled_time.hour
        if hour < 8 or hour > 18:
            time_score = 0.15
        else:
            time_score = 0.05

        # Day of week (15% weight)
        # Mondays and Fridays have higher no-show rates
        day_of_week = booking.scheduled_time.weekday()
        if day_of_week in [0, 4]:  # Monday, Friday
            day_score = 0.15
        else:
            day_score = 0.05

        # Total probability
        probability = history_score + advance_score + time_score + day_score

        # Risk classification
        if probability >= 0.4:
            risk = "high"
        elif probability >= 0.25:
            risk = "medium"
        else:
            risk = "low"

        return {
            "booking_id": str(booking_id),
            "no_show_probability": round(probability, 2),
            "risk_level": risk,
            "factors": {
                "customer_history": round(history_score, 2),
                "advance_booking": round(advance_score, 2),
                "time_of_day": round(time_score, 2),
                "day_of_week": round(day_score, 2),
            },
            "recommendation": "Send reminder" if risk in ["high", "medium"] else "No action needed",
        }
