from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BookingConflictError, NotFoundException
from app.core.tenant_context import get_current_tenant
from app.core.websocket import manager as ws_manager
from app.domain.booking.models import (
    BOOKING_STATUS_TRANSITIONS,
    Booking,
    BookingStatus,
    FieldAgent,
    PaymentTiming,
    Provider,
    Service,
)
from app.domain.booking.persistence import write_with_journal
from app.domain.booking.read_queries import availability_statement, booking_statement, enriched_statement


class BookingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _apply_tenant_filter(self, query):
        """Apply tenant filter to query"""
        tenant_id = get_current_tenant()
        if tenant_id:
            return query.where(Booking.tenant_id == tenant_id)
        return query

    async def check_availability(
        self,
        provider_id: UUID,
        scheduled_time: datetime,
        duration_minutes: int,
        exclude_booking_id: Optional[UUID] = None,
    ) -> bool:
        """Check half-open intervals; callers creating bookings must lock the provider first."""
        tenant = get_current_tenant()
        params = {"provider_id": provider_id, "scheduled_time": scheduled_time, "duration_minutes": duration_minutes}
        if tenant:
            params["tenant_id"] = tenant
        if exclude_booking_id:
            params["exclude_id"] = exclude_booking_id
        result = await self.session.execute(availability_statement(bool(tenant), bool(exclude_booking_id)), params)
        return result.first() is None

    async def create(
        self,
        customer_id: UUID,
        provider_id: UUID,
        service_id: UUID,
        scheduled_time: datetime,
        duration_minutes: int,
        location_postcode: str,
        base_price_cents: int,
        description: Optional[str] = None,
        location_address: Optional[str] = None,
        payment_timing: PaymentTiming = PaymentTiming.BEFORE_SERVICE,
        deposit_percentage: int = 0,
    ) -> Booking:
        """Create a new booking with conflict detection"""
        # The API/schema layer defines a parallel PaymentTiming enum (same values, different
        # class); coerce to the model enum so SQLAlchemy's Enum validation accepts it.
        if not isinstance(payment_timing, PaymentTiming):
            payment_timing = PaymentTiming(getattr(payment_timing, "value", payment_timing))

        # The caller owns the outer transaction and rolls it back on failure.
        # A nested savepoint adds two round trips without another atomicity boundary.
        tenant_id = get_current_tenant()
        if not tenant_id:
            raise ValueError("Tenant context required")
        # Existing booking locks cannot protect an empty schedule. Serialize on
        # the provider row, held until the outer transaction commits/rolls back.
        service_ref = (
            select(Service.id)
            .where(Service.id == service_id, Service.provider_id == Provider.id, Service.tenant_id == tenant_id)
            .correlate(Provider)
            .scalar_subquery()
        )
        provider = (
            await self.session.execute(
                select(Provider.id, service_ref.label("service_id"))
                .where(Provider.id == provider_id, Provider.tenant_id == tenant_id)
                .with_for_update(of=Provider)
            )
        ).one_or_none()
        if provider is None:
            raise NotFoundException("Provider")
        if provider.service_id is None:
            raise NotFoundException("Service")
        is_available = await self.check_availability(provider_id, scheduled_time, duration_minutes)

        if not is_available:
            raise BookingConflictError("Time slot not available for this provider")

        booking_id = uuid4()
        return await write_with_journal(
            self.session,
            create=True,
            values=dict(
                id=booking_id,
                tenant_id=tenant_id,
                customer_id=customer_id,
                provider_id=provider_id,
                service_id=service_id,
                scheduled_time=scheduled_time,
                duration_minutes=duration_minutes,
                description=description,
                status=BookingStatus.PENDING,
                location_postcode=location_postcode,
                location_address=location_address,
                base_price_cents=base_price_cents,
                payment_timing=payment_timing,
                deposit_percentage=deposit_percentage,
                deposit_paid_cents=0,
                total_paid_cents=0,
                version=1,
                discount_cents=0,
                route_order=0,
            ),
            action="create",
            old_values=None,
            new_values={
                "customer_id": str(customer_id),
                "provider_id": str(provider_id),
                "scheduled_time": scheduled_time.isoformat(),
                "status": BookingStatus.PENDING.value,
            },
            user_id=customer_id,
            event_type="booking.created",
            event_data={
                "customer_id": str(customer_id),
                "provider_id": str(provider_id),
                "service_id": str(service_id),
                "scheduled_time": scheduled_time.isoformat(),
                "base_price_cents": base_price_cents,
            },
        )

    async def get_by_id(self, booking_id: UUID, *, with_relationships: bool = True) -> Optional[Booking]:
        """Get booking by ID"""
        tenant = get_current_tenant()
        params = {"booking_id": booking_id}
        if tenant:
            params["tenant_id"] = tenant
        result = await self.session.execute(booking_statement(bool(tenant), with_relationships), params)
        return result.scalar_one_or_none()

    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        status: Optional[BookingStatus] = None,
        customer_id: Optional[UUID] = None,
        provider_id: Optional[UUID] = None,
        field_agent_id: Optional[UUID] = None,
    ) -> List[Booking]:
        'List bookings with optional filters.'
        query = select(Booking).order_by(Booking.scheduled_time.desc())

        if status:
            query = query.where(Booking.status == status)
        if customer_id:
            query = query.where(Booking.customer_id == customer_id)
        if provider_id:
            query = query.where(Booking.provider_id == provider_id)
        if field_agent_id:
            query = query.where(Booking.field_agent_id == field_agent_id)

        query = self._apply_tenant_filter(query).offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_enriched(
        self,
        skip: int = 0,
        limit: int = 100,
        status: Optional[BookingStatus] = None,
        customer_id: Optional[UUID] = None,
        provider_id: Optional[UUID] = None,
        field_agent_id: Optional[UUID] = None,
    ) -> list:
        """Return the same public fields without hydrating five ORM entity graphs."""
        tenant = get_current_tenant()
        filters = {
            name: value
            for name, value in [("customer_id", customer_id), ("provider_id", provider_id), ("field_agent_id", field_agent_id)]
            if value
        }
        params = {"skip": skip, "limit": limit, **filters}
        if tenant:
            params["tenant_id"] = tenant
        if status:
            params["booking_status"] = status
        result = await self.session.execute(enriched_statement(tuple(filters), bool(status), bool(tenant)), params)
        return list(result.mappings().all())

    async def get_by_customer(self, customer_id: UUID, limit: int = 50) -> List[Booking]:
        """Get bookings for a customer"""
        query = select(Booking).where(Booking.customer_id == customer_id).order_by(Booking.scheduled_time.desc()).limit(limit)
        query = self._apply_tenant_filter(query)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_provider(self, provider_id: UUID, limit: int = 50) -> List[Booking]:
        """Get bookings for a provider"""
        query = select(Booking).where(Booking.provider_id == provider_id).order_by(Booking.scheduled_time.desc()).limit(limit)
        query = self._apply_tenant_filter(query)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_status(
        self,
        booking_id: UUID,
        new_status: BookingStatus,
        expected_version: Optional[int] = None,
        *,
        loaded_booking: Optional[Booking] = None,
    ) -> Optional[Booking]:
        """Update booking status, enforcing the state-machine transition table.

        If ``expected_version`` is supplied, it is checked against the loaded row to
        detect concurrent modifications. The atomic statement compares the tenant
        and original version, increments the version, and journals only a matching
        update. A stale write returns 409 without extra audit/outbox rows.
        """
        from app.core.exceptions import AppException

        booking = loaded_booking
        if booking is not None:
            # A route may reuse the row it already loaded and authorized, but it
            # cannot pass an unscoped/detached object to skip repository scoping.
            if (
                booking.id != booking_id
                or booking.tenant_id != get_current_tenant()
                or inspect(booking).session is not self.session.sync_session
            ):
                raise ValueError("Booking must belong to this session and tenant")
        else:
            booking = await self.get_by_id(booking_id, with_relationships=False)
        if not booking:
            return None

        if expected_version is not None and booking.version != expected_version:
            raise AppException(
                status_code=409,
                error_code="stale_write",
                message="Booking was modified by another request; please refresh and retry",
            )

        old_status = booking.status
        allowed = BOOKING_STATUS_TRANSITIONS.get(old_status, set())
        if new_status not in allowed:
            raise AppException(
                status_code=422,
                error_code="invalid_transition",
                message=f"Cannot transition booking from '{old_status.value}' to '{new_status.value}'",
            )
        event_type = {
            BookingStatus.CONFIRMED: "booking.confirmed",
            BookingStatus.COMPLETED: "booking.completed",
            BookingStatus.CANCELLED: "booking.cancelled",
        }.get(new_status)
        booking = await write_with_journal(
            self.session,
            create=False,
            values={
                "id": booking.id,
                "tenant_id": booking.tenant_id,
                "version": booking.version,
                "status": new_status,
                "completed_at": datetime.now(timezone.utc) if new_status == BookingStatus.COMPLETED else booking.completed_at,
            },
            action="update_status",
            old_values={"status": old_status.value},
            new_values={"status": new_status.value},
            event_type=event_type,
            event_data={"old_status": old_status.value, "new_status": new_status.value},
        )
        if booking is None:
            await self.session.rollback()
            raise AppException(
                status_code=409,
                error_code="stale_write",
                message="Booking was modified by another request; please refresh and retry",
            )

        # (not gated on Kafka -- unlike the DomainEvent publish below, this covers
        # every valid transition, including the granular ones with no Kafka event
        # mapped, e.g. ON_MY_WAY/ARRIVED/DELAYED/NO_SHOW). Best-effort like every
        # other WS send: never raises, degrades to a no-op if nobody's connected.
        await ws_manager.broadcast_to_booking(
            {
                "type": "booking_status_update",
                "booking_id": str(booking.id),
                "old_status": old_status.value,
                "new_status": new_status.value,
            },
            customer_id=booking.customer_id,
            provider_id=booking.provider_id,
            agent_id=booking.field_agent_id,
        )

        return booking
