"""Kafka consumer handlers for payment domain events."""

import logging
from typing import Any

from app.services.notification_service import notification_service

logger = logging.getLogger(__name__)


async def handle_payment_completed(event: dict[str, Any]) -> None:
    """Notify the customer that their payment was received."""
    data = event.get("data", {})
    customer_email = data.get("customer_email")
    customer_name = data.get("customer_name", "Customer")
    amount_pence = data.get("amount_cents", 0)
    booking_id = data.get("booking_id", "")

    if not customer_email:
        logger.warning("payment.completed event missing customer_email (payment=%s)", event.get("aggregate_id"))
        return

    amount_str = f"£{amount_pence / 100:.2f}"
    await notification_service.send_email(
        to_email=customer_email,
        subject=f"Payment of {amount_str} received",
        body=(
            f"<p>Hi {customer_name},</p>"
            f"<p>We've received your payment of <strong>{amount_str}</strong> "
            + (f"for booking {booking_id[:8].upper()}. " if booking_id else ". ")
            + f"Thank you!</p>"
        ),
    )
    logger.info("payment.completed notification sent to %s", customer_email)


async def handle_payment_failed(event: dict[str, Any]) -> None:
    """Notify the customer that their payment failed."""
    data = event.get("data", {})
    customer_email = data.get("customer_email")
    customer_name = data.get("customer_name", "Customer")
    booking_id = data.get("booking_id", "")

    if not customer_email:
        logger.warning("payment.failed event missing customer_email (payment=%s)", event.get("aggregate_id"))
        return

    await notification_service.send_email(
        to_email=customer_email,
        subject="Action required — payment failed",
        body=(
            f"<p>Hi {customer_name},</p>"
            f"<p>We were unable to process your payment"
            + (f" for booking {booking_id[:8].upper()}" if booking_id else "")
            + f". Please update your payment details or contact us.</p>"
        ),
    )
    logger.info("payment.failed notification sent to %s", customer_email)


PAYMENT_HANDLERS = {
    "payment.completed": handle_payment_completed,
    "payment.failed": handle_payment_failed,
}


async def dispatch_payment_event(event: dict[str, Any]) -> None:
    """Route a payment domain event to the correct handler."""
    event_type = event.get("event_type")
    handler = PAYMENT_HANDLERS.get(event_type)
    if handler is None:
        logger.debug("No handler registered for payment event type: %s", event_type)
        return
    await handler(event)
