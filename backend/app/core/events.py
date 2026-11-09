from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class DomainEvent(BaseModel):
    """Base class for all domain events"""

    model_config = ConfigDict(frozen=True)

    event_id: UUID = Field(default_factory=uuid4)
    event_type: str
    aggregate_id: UUID
    aggregate_type: str
    tenant_id: UUID | None = None
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data: dict[str, Any]


# Booking Events
class BookingCreated(DomainEvent):
    event_type: str = "booking.created"
    aggregate_type: str = "booking"


class BookingConfirmed(DomainEvent):
    event_type: str = "booking.confirmed"
    aggregate_type: str = "booking"


class BookingAssigned(DomainEvent):
    event_type: str = "booking.assigned"
    aggregate_type: str = "booking"


class BookingCompleted(DomainEvent):
    event_type: str = "booking.completed"
    aggregate_type: str = "booking"


class BookingCancelled(DomainEvent):
    event_type: str = "booking.cancelled"
    aggregate_type: str = "booking"


# Payment Events
class PaymentCreated(DomainEvent):
    event_type: str = "payment.created"
    aggregate_type: str = "payment"


class PaymentCompleted(DomainEvent):
    event_type: str = "payment.completed"
    aggregate_type: str = "payment"


class PaymentFailed(DomainEvent):
    event_type: str = "payment.failed"
    aggregate_type: str = "payment"


class PaymentRefunded(DomainEvent):
    event_type: str = "payment.refunded"
    aggregate_type: str = "payment"
