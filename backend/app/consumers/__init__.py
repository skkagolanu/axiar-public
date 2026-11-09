"""Domain event consumers — registered during app lifespan in main.py."""

from app.consumers.booking_handlers import dispatch_booking_event
from app.consumers.payment_handlers import dispatch_payment_event

__all__ = ["dispatch_booking_event", "dispatch_payment_event"]
