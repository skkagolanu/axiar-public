from uuid import UUID

from app.core.cqrs.queries import Query, QueryHandler
from app.core.database import db_manager
from app.domain.booking.repository import BookingRepository
from app.domain.booking.schemas import BookingRead


class GetBookingQuery(Query):
    booking_id: UUID


class GetCustomerBookingsQuery(Query):
    customer_id: UUID
    limit: int = 50


class GetProviderBookingsQuery(Query):
    provider_id: UUID
    limit: int = 50


class GetBookingHandler(QueryHandler[GetBookingQuery, BookingRead | None]):
    """Handle get booking query"""

    async def handle(self, query: GetBookingQuery) -> BookingRead | None:
        async with db_manager.get_session() as session:
            repo = BookingRepository(session)
            booking = await repo.get_by_id(query.booking_id)
            return BookingRead.model_validate(booking) if booking else None


class GetCustomerBookingsHandler(QueryHandler[GetCustomerBookingsQuery, list[BookingRead]]):
    """Handle get customer bookings query"""

    async def handle(self, query: GetCustomerBookingsQuery) -> list[BookingRead]:
        async with db_manager.get_session() as session:
            repo = BookingRepository(session)
            bookings = await repo.get_by_customer(query.customer_id, query.limit)
            return [BookingRead.model_validate(b) for b in bookings]


class GetProviderBookingsHandler(QueryHandler[GetProviderBookingsQuery, list[BookingRead]]):
    """Handle get provider bookings query"""

    async def handle(self, query: GetProviderBookingsQuery) -> list[BookingRead]:
        async with db_manager.get_session() as session:
            repo = BookingRepository(session)
            bookings = await repo.get_by_provider(query.provider_id, query.limit)
            return [BookingRead.model_validate(b) for b in bookings]
