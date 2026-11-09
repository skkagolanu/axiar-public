from datetime import datetime
from uuid import UUID

from app.core.cqrs.commands import Command, CommandHandler
from app.core.database import db_manager
from app.core.exceptions import ValidationException
from app.domain.booking.models import BookingStatus, PaymentTiming
from app.domain.booking.repository import BookingRepository
from app.domain.promo.repository import PromoCodeRepository


class CreateBookingCommand(Command):
    customer_id: UUID
    provider_id: UUID
    service_id: UUID
    scheduled_time: datetime
    duration_minutes: int
    location_postcode: str
    base_price_cents: int
    description: str | None = None
    location_address: str | None = None
    # Kept in parity with the REST BookingCreate schema so the CQRS path doesn't silently
    # drop pricing/promo fields. payment_timing is a plain str (the schema enum is a
    # parallel class); BookingRepository.create coerces it to the model enum.
    payment_timing: str = PaymentTiming.BEFORE_SERVICE.value
    deposit_percentage: int = 0
    promo_code: str | None = None


class UpdateBookingStatusCommand(Command):
    booking_id: UUID
    new_status: BookingStatus


class CreateBookingHandler(CommandHandler[CreateBookingCommand, UUID]):
    """Handle booking creation"""

    async def handle(self, command: CreateBookingCommand) -> UUID:
        async with db_manager.get_session() as session:
            repo = BookingRepository(session)
            promo_repo = PromoCodeRepository(session)

            discount_cents = 0
            if command.promo_code:
                valid, discount_cents, message = await promo_repo.validate_and_apply(
                    command.promo_code, command.base_price_cents
                )
                if not valid:
                    raise ValidationException(message)

            booking = await repo.create(
                customer_id=command.customer_id,
                provider_id=command.provider_id,
                service_id=command.service_id,
                scheduled_time=command.scheduled_time,
                duration_minutes=command.duration_minutes,
                location_postcode=command.location_postcode,
                base_price_cents=command.base_price_cents,
                description=command.description,
                location_address=command.location_address,
                payment_timing=command.payment_timing,
                deposit_percentage=command.deposit_percentage,
            )

            if discount_cents > 0 and command.promo_code:
                booking.promo_code = command.promo_code.upper()
                booking.discount_cents = discount_cents
                await promo_repo.increment_usage(command.promo_code)

            final_price = booking.base_price_cents - discount_cents
            if booking.payment_timing == PaymentTiming.SPLIT_PAYMENT:
                booking.deposit_paid_cents = int(final_price * booking.deposit_percentage / 100)

            await session.commit()
            return booking.id


class UpdateBookingStatusHandler(CommandHandler[UpdateBookingStatusCommand, bool]):
    """Handle booking status update"""

    async def handle(self, command: UpdateBookingStatusCommand) -> bool:
        async with db_manager.get_session() as session:
            repo = BookingRepository(session)
            booking = await repo.update_status(command.booking_id, command.new_status)
            if booking:
                await session.commit()
                return True
            return False
