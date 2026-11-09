from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BookingStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    ASSIGNED = "assigned"
    ON_MY_WAY = "on_my_way"
    ARRIVED = "arrived"
    DELAYED = "delayed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PaymentTiming(str, Enum):
    BEFORE_SERVICE = "before_service"
    AFTER_SERVICE = "after_service"
    SPLIT_PAYMENT = "split_payment"


class BookingCreate(BaseModel):
    provider_id: UUID
    service_id: UUID
    scheduled_time: datetime
    duration_minutes: int = Field(..., ge=15, le=480)
    description: Optional[str] = None
    location_postcode: str = Field(..., min_length=5, max_length=10)
    location_address: Optional[str] = None
    base_price_cents: int = Field(..., ge=100)
    payment_timing: PaymentTiming = PaymentTiming.BEFORE_SERVICE
    deposit_percentage: int = Field(default=0, ge=0, le=100)
    promo_code: Optional[str] = None

    @field_validator("scheduled_time")
    @classmethod
    def validate_future_time(cls, v):
        if v <= datetime.now(timezone.utc):
            raise ValueError("Booking time must be in the future")
        return v

    @field_validator("deposit_percentage")
    @classmethod
    def validate_deposit(cls, v, info):
        if info.data.get("payment_timing") == PaymentTiming.SPLIT_PAYMENT and v == 0:
            raise ValueError("Deposit percentage required for split payments")
        return v


class BookingUpdate(BaseModel):
    scheduled_time: Optional[datetime] = None
    description: Optional[str] = None
    status: Optional[BookingStatus] = None


class BookingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID
    provider_id: UUID
    service_id: UUID
    field_agent_id: Optional[UUID]
    scheduled_time: datetime
    duration_minutes: int
    description: Optional[str]
    status: BookingStatus
    location_postcode: str
    location_address: Optional[str]
    base_price_cents: int
    deposit_paid_cents: int
    total_paid_cents: int
    payment_timing: PaymentTiming
    deposit_percentage: int
    promo_code: Optional[str]
    discount_cents: int
    created_at: datetime


def _full_name(u) -> Optional[str]:
    if u is None:
        return None
    name = f"{getattr(u, 'first_name', '') or ''} {getattr(u, 'last_name', '') or ''}".strip()
    return name or None


class BookingReadEnriched(BookingRead):
    """BookingRead + display fields resolved from the eager-loaded relationships
    (customer / service / field_agent.user). Built in one query — see Booking's
    ``lazy="joined"`` — so a jobs grid renders without N+1 follow-up fetches.
    """

    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    service_name: Optional[str] = None
    service_type: Optional[str] = None
    assigned_agent_id: Optional[UUID] = None
    assigned_agent_name: Optional[str] = None

    @classmethod
    def from_booking(cls, b) -> "BookingReadEnriched":
        customer = getattr(b, "customer", None)
        service = getattr(b, "service", None)
        agent = getattr(b, "field_agent", None)
        agent_user = getattr(agent, "user", None) if agent is not None else None
        return cls(
            **BookingRead.model_validate(b).model_dump(),
            customer_name=_full_name(customer),
            customer_phone=getattr(customer, "phone", None),
            service_name=getattr(service, "name", None),
            service_type=getattr(service, "service_type", None),
            assigned_agent_id=getattr(agent, "id", None),
            assigned_agent_name=_full_name(agent_user),
        )


class ProviderCreate(BaseModel):
    business_name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    business_phone: Optional[str] = None
    business_email: Optional[str] = None
    website_url: Optional[str] = None
    service_radius_km: int = Field(default=10, ge=1, le=100)


class ProviderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    business_name: str
    description: Optional[str]
    business_phone: Optional[str]
    business_email: Optional[str]
    website_url: Optional[str]
    service_radius_km: int
    average_rating: float
    total_reviews: int
    is_active: bool
    created_at: datetime


class ServiceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    service_type: str = Field(..., min_length=1, max_length=100)
    base_price_cents: int = Field(..., ge=100)
    duration_minutes: int = Field(..., ge=15, le=480)


class ServiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider_id: UUID
    name: str
    description: Optional[str]
    service_type: str
    base_price_cents: int
    duration_minutes: int
    is_available: bool
    created_at: datetime


class GuestBookingCreate(BaseModel):
    email: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    booking_data: BookingCreate
