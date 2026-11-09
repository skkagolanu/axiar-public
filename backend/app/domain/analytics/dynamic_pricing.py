"""
Dynamic Pricing using Surge Pricing Algorithm
Industry standard: Uber/Lyft style demand-based pricing
"""

from datetime import datetime, timedelta
from typing import Dict
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.booking.models import Booking, BookingStatus, FieldAgent, Service


class DynamicPricingService:
    """Calculate dynamic prices based on demand and supply"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def calculate_demand_supply_ratio(self, service_id: UUID, target_time: datetime) -> float:
        """Calculate demand/supply ratio for a time window"""
        # Count bookings in 2-hour window around target time
        window_start = target_time - timedelta(hours=1)
        window_end = target_time + timedelta(hours=1)

        result = await self.session.execute(
            select(func.count(Booking.id)).where(
                Booking.service_id == service_id, Booking.scheduled_time >= window_start, Booking.scheduled_time <= window_end
            )
        )

        demand = result.scalar() or 0
        supply = await self._calculate_supply(service_id, window_start, window_end)

        return demand / supply if supply > 0 else 0

    async def _calculate_supply(self, service_id: UUID, window_start: datetime, window_end: datetime) -> int:
        """Count available field agents for the requested booking window.

        Supply = the provider's active+available field agents, minus whichever of them
        are already assigned to another non-terminal booking whose scheduled window
        overlaps this one (an agent flagged "available" in general isn't actually free
        if they're already booked solid during this exact window).
        """
        service_result = await self.session.execute(select(Service.provider_id).where(Service.id == service_id))
        provider_id = service_result.scalar_one_or_none()
        if provider_id is None:
            return 0

        total_result = await self.session.execute(
            select(func.count(FieldAgent.id)).where(
                FieldAgent.provider_id == provider_id,
                FieldAgent.is_active.is_(True),
                FieldAgent.is_available.is_(True),
            )
        )
        total_agents = total_result.scalar() or 0

        busy_result = await self.session.execute(
            select(func.count(func.distinct(Booking.field_agent_id))).where(
                and_(
                    Booking.provider_id == provider_id,
                    Booking.field_agent_id.is_not(None),
                    Booking.status.in_(
                        [
                            BookingStatus.PENDING,
                            BookingStatus.CONFIRMED,
                            BookingStatus.ASSIGNED,
                            BookingStatus.ON_MY_WAY,
                            BookingStatus.ARRIVED,
                            BookingStatus.DELAYED,
                            BookingStatus.IN_PROGRESS,
                        ]
                    ),
                    Booking.scheduled_time < window_end,
                    Booking.scheduled_time + func.make_interval(0, 0, 0, 0, 0, Booking.duration_minutes) > window_start,
                )
            )
        )
        busy_agents = busy_result.scalar() or 0

        return max(total_agents - busy_agents, 0)

    async def get_surge_multiplier(self, service_id: UUID, target_time: datetime) -> Dict:
        """
        Calculate surge pricing multiplier
        Industry standard: 1.0x (normal) to 3.0x (peak)
        """
        # Base multiplier
        multiplier = 1.0

        # Factor 1: Demand/Supply ratio (up to 1.5x)
        ds_ratio = await self.calculate_demand_supply_ratio(service_id, target_time)
        if ds_ratio > 1.5:
            multiplier += 1.0  # High demand
        elif ds_ratio > 1.0:
            multiplier += 0.5  # Medium demand

        # Factor 2: Time of day (up to 0.3x)
        hour = target_time.hour
        if 17 <= hour <= 19:  # Evening rush
            multiplier += 0.3
        elif 7 <= hour <= 9:  # Morning rush
            multiplier += 0.2

        # Factor 3: Day of week (up to 0.2x)
        day_of_week = target_time.weekday()
        if day_of_week in [5, 6]:  # Weekend
            multiplier += 0.2

        # Cap at 3.0x
        multiplier = min(multiplier, 3.0)

        return {
            "multiplier": round(multiplier, 2),
            "demand_supply_ratio": round(ds_ratio, 2),
            "peak_time": hour in [7, 8, 9, 17, 18, 19],
        }

    async def calculate_dynamic_price(self, service_id: UUID, target_time: datetime) -> Dict:
        """Calculate final dynamic price for a service"""
        # Get base price
        result = await self.session.execute(select(Service).where(Service.id == service_id))
        service = result.scalar_one_or_none()

        if not service:
            return {"error": "Service not found"}

        base_price_cents = service.base_price_cents

        # Get surge multiplier
        surge = await self.get_surge_multiplier(service_id, target_time)
        multiplier = surge["multiplier"]

        # Calculate final price
        dynamic_price_cents = int(base_price_cents * multiplier)

        # Apply min/max constraints if set
        if service.min_price_cents:
            dynamic_price_cents = max(dynamic_price_cents, service.min_price_cents)
        if service.max_price_cents:
            dynamic_price_cents = min(dynamic_price_cents, service.max_price_cents)

        return {
            "service_id": str(service_id),
            "base_price_cents": base_price_cents,
            "surge_multiplier": multiplier,
            "dynamic_price_cents": dynamic_price_cents,
            "savings_cents": base_price_cents - dynamic_price_cents if multiplier < 1.0 else 0,
            "surcharge_cents": dynamic_price_cents - base_price_cents if multiplier > 1.0 else 0,
            "factors": surge,
        }
