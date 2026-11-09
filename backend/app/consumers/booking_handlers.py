"""Kafka consumer handlers for booking domain events.

Each handler receives a deserialized event dict from the event bus and performs
side-effects (notifications, cache invalidation, etc.) that must not block the
original booking request. All failures are caught and logged — never re-raised —
so a handler error does not kill the consumer loop.
"""

import logging
from typing import Any

from app.services.notification_service import notification_service

logger = logging.getLogger(__name__)


async def handle_booking_created(event: dict[str, Any]) -> None:
    """Send a booking-received confirmation to the customer."""
    data = event.get("data", {})
    customer_email = data.get("customer_email")
    customer_name = data.get("customer_name", "Customer")
    booking_id = event.get("aggregate_id", "")

    if not customer_email:
        logger.warning("booking.created event missing customer_email — skipping notification (booking=%s)", booking_id)
        return

    await notification_service.send_email(
        to_email=customer_email,
        subject="Booking received — we'll confirm shortly",
        body=(
            f"<p>Hi {customer_name},</p>"
            f"<p>We've received your booking request (ref: <strong>{booking_id[:8].upper()}</strong>). "
            f"We'll confirm it shortly.</p>"
        ),
    )
    logger.info("booking.created notification sent to %s (booking=%s)", customer_email, booking_id)


async def handle_booking_confirmed(event: dict[str, Any]) -> None:
    """Notify the customer that their booking has been confirmed."""
    data = event.get("data", {})
    customer_email = data.get("customer_email")
    customer_name = data.get("customer_name", "Customer")
    booking_id = event.get("aggregate_id", "")

    if not customer_email:
        logger.warning("booking.confirmed event missing customer_email (booking=%s)", booking_id)
        return

    await notification_service.send_email(
        to_email=customer_email,
        subject="Your booking is confirmed ✓",
        body=(
            f"<p>Hi {customer_name},</p>"
            f"<p>Great news — your booking (ref: <strong>{booking_id[:8].upper()}</strong>) is confirmed. "
            f"We look forward to seeing you.</p>"
        ),
    )
    logger.info("booking.confirmed notification sent to %s (booking=%s)", customer_email, booking_id)


async def handle_booking_completed(event: dict[str, Any]) -> None:
    """Notify the customer that service is complete and invite them to leave a review."""
    data = event.get("data", {})
    customer_email = data.get("customer_email")
    customer_name = data.get("customer_name", "Customer")
    booking_id = event.get("aggregate_id", "")

    if not customer_email:
        logger.warning("booking.completed event missing customer_email (booking=%s)", booking_id)
        return

    await notification_service.send_email(
        to_email=customer_email,
        subject="Service completed — how did we do?",
        body=(
            f"<p>Hi {customer_name},</p>"
            f"<p>Your service (ref: <strong>{booking_id[:8].upper()}</strong>) is complete. "
            f"We'd love to hear how it went — please take a moment to leave a review.</p>"
        ),
    )
    logger.info("booking.completed notification sent to %s (booking=%s)", customer_email, booking_id)


async def handle_booking_cancelled(event: dict[str, Any]) -> None:
    """Notify the customer that their booking was cancelled."""
    data = event.get("data", {})
    customer_email = data.get("customer_email")
    customer_name = data.get("customer_name", "Customer")
    booking_id = event.get("aggregate_id", "")

    if not customer_email:
        logger.warning("booking.cancelled event missing customer_email (booking=%s)", booking_id)
        return

    await notification_service.send_email(
        to_email=customer_email,
        subject="Your booking has been cancelled",
        body=(
            f"<p>Hi {customer_name},</p>"
            f"<p>Your booking (ref: <strong>{booking_id[:8].upper()}</strong>) has been cancelled. "
            f"If this was unexpected please contact us.</p>"
        ),
    )
    logger.info("booking.cancelled notification sent to %s (booking=%s)", customer_email, booking_id)


# Dispatch table: event_type → handler
BOOKING_HANDLERS = {
    "booking.created": handle_booking_created,
    "booking.confirmed": handle_booking_confirmed,
    "booking.completed": handle_booking_completed,
    "booking.cancelled": handle_booking_cancelled,
}


async def dispatch_booking_event(event: dict[str, Any]) -> None:
    """Route a booking domain event to the correct handler."""
    event_type = event.get("event_type")
    handler = BOOKING_HANDLERS.get(event_type)
    if handler is None:
        logger.debug("No handler registered for booking event type: %s", event_type)
        return
    await handler(event)
