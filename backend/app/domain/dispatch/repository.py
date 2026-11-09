from datetime import datetime
from typing import List, Optional, Tuple
from uuid import UUID

from geoalchemy2.functions import ST_Distance
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_context import get_current_tenant
from app.domain.booking.models import Booking, BookingStatus, FieldAgent


class DispatchRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _apply_tenant_filter(self, query):
        """Apply tenant filter to queries against FieldAgent."""
        tenant_id = get_current_tenant()
        if tenant_id:
            return query.where(FieldAgent.tenant_id == tenant_id)
        return query

    def _apply_booking_tenant_filter(self, query):
        """Apply tenant filter to queries against Booking."""
        tenant_id = get_current_tenant()
        if tenant_id:
            return query.where(Booking.tenant_id == tenant_id)
        return query

    async def find_available_agents(
        self,
        latitude: float,
        longitude: float,
        max_distance_km: float = 50.0,
        required_skills: Optional[List[str]] = None,
    ) -> List[Tuple[FieldAgent, float]]:
        """Find available field agents near a location"""
        point = f"POINT({longitude} {latitude})"

        query = select(
            FieldAgent,
            func.ST_Distance(FieldAgent.current_location, func.ST_GeogFromText(point)).label("distance_meters"),
        ).where(
            and_(
                FieldAgent.is_available == True,  # noqa: E712
                FieldAgent.is_active == True,  # noqa: E712
                func.ST_DWithin(
                    FieldAgent.current_location,
                    func.ST_GeogFromText(point),
                    max_distance_km * 1000,
                ),
            )
        )

        # Never dispatch an agent from another tenant.
        query = self._apply_tenant_filter(query)

        if required_skills:
            query = query.where(FieldAgent.skills.op("&&")(required_skills))

        query = query.order_by("distance_meters")

        result = await self.session.execute(query)
        return [(row[0], row[1]) for row in result.all()]

    async def get_agent_workload(self, agent_id: UUID) -> int:
        """Get number of active bookings for an agent"""
        query = self._apply_booking_tenant_filter(
            select(func.count(Booking.id)).where(
                and_(
                    Booking.field_agent_id == agent_id,
                    Booking.status.in_(
                        [
                            BookingStatus.ASSIGNED,
                            BookingStatus.IN_PROGRESS,
                        ]
                    ),
                )
            )
        )
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def assign_agent_to_booking(self, booking_id: UUID, agent_id: UUID) -> Optional[Booking]:
        """Assign field agent to booking"""
        query = self._apply_booking_tenant_filter(select(Booking).where(Booking.id == booking_id))
        result = await self.session.execute(query)
        booking = result.scalar_one_or_none()

        if not booking:
            return None

        booking.field_agent_id = agent_id
        booking.status = BookingStatus.ASSIGNED
        # version is managed by SQLAlchemy's optimistic lock (version_id_col on Booking).

        await self.session.flush()
        await self.session.refresh(booking)

        return booking
