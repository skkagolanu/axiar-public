"""Booking-demand estimates from moving averages and weekday patterns."""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.booking.models import Booking

# (day, booking_count) ordered oldest → newest
DailyCounts = List[Tuple[datetime, int]]


def _mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


class DemandForecastService:
    """Forecast booking demand using historical data"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_historical_data(self, days: int = 90) -> DailyCounts:
        """Get historical booking counts per day, oldest first."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        day_trunc = func.date_trunc("day", Booking.scheduled_time)

        result = await self.session.execute(
            select(
                day_trunc.label("ds"),
                func.count(Booking.id).label("y"),
            )
            .where(Booking.scheduled_time >= cutoff)
            .group_by(day_trunc)
            .order_by(day_trunc)
        )

        return [(row.ds, row.y) for row in result]

    async def forecast_demand(self, days_ahead: int = 30) -> List[Dict]:
        """
        Forecast booking demand for next N days.
        Heuristic: 7-day moving average + weekday pattern, not a real forecasting model.
        """
        rows = await self.get_historical_data()
        counts = [float(y) for _, y in rows]

        if len(rows) < 7:
            # Not enough data, return average (10 is the cold-start default)
            avg = _mean(counts) if counts else 10.0
            return [
                {"date": (datetime.now(timezone.utc) + timedelta(days=i)).date().isoformat(), "predicted_bookings": int(avg)}
                for i in range(days_ahead)
            ]

        # Simple moving average forecast (7-day window)
        window = min(7, len(rows))
        recent_avg = _mean(counts[-window:])

        # Detect weekly pattern. date.weekday() is Monday=0, matching the
        # pandas dayofweek this replaced.
        weekly_pattern: Dict[int, float]
        if len(rows) >= 14:
            by_weekday: Dict[int, List[float]] = defaultdict(list)
            for ds, y in rows:
                by_weekday[ds.weekday()].append(float(y))
            weekly_pattern = {day: _mean(values) for day, values in by_weekday.items()}
        else:
            weekly_pattern = {i: recent_avg for i in range(7)}

        forecasts = []
        for i in range(days_ahead):
            future_date = datetime.now(timezone.utc) + timedelta(days=i)
            day_of_week = future_date.weekday()
            predicted = int(weekly_pattern.get(day_of_week, recent_avg))

            forecasts.append({"date": future_date.date().isoformat(), "predicted_bookings": predicted, "confidence": "medium"})

        return forecasts

    async def get_peak_hours(self) -> Dict[int, float]:
        """Identify peak booking hours"""
        hour_extract = func.extract("hour", Booking.scheduled_time)

        result = await self.session.execute(
            select(hour_extract.label("hour"), func.count(Booking.id).label("count"))
            .group_by(hour_extract)
            .order_by(func.count(Booking.id).desc())
        )

        hours = {int(row.hour): row.count for row in result}
        total = sum(hours.values())

        if total == 0:
            return {}

        # Return as percentage
        return {hour: (count / total) * 100 for hour, count in hours.items()}
