from datetime import date, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Set
from uuid import UUID, uuid4

from geoalchemy2 import Geography
from sqlalchemy import Boolean, Column, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import Float, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSON as PG_JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.domain.user.models import User


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
    NO_SHOW = "no_show"


# Allowed booking-state transitions; terminal states have no outgoing transitions.
BOOKING_STATUS_TRANSITIONS: Dict[BookingStatus, Set[BookingStatus]] = {
    BookingStatus.PENDING: {BookingStatus.CONFIRMED, BookingStatus.CANCELLED},
    BookingStatus.CONFIRMED: {BookingStatus.ASSIGNED, BookingStatus.CANCELLED, BookingStatus.NO_SHOW},
    BookingStatus.ASSIGNED: {BookingStatus.ON_MY_WAY, BookingStatus.CANCELLED, BookingStatus.NO_SHOW},
    BookingStatus.ON_MY_WAY: {
        BookingStatus.ARRIVED,
        BookingStatus.DELAYED,
        BookingStatus.CANCELLED,
        BookingStatus.NO_SHOW,
    },
    BookingStatus.ARRIVED: {
        BookingStatus.IN_PROGRESS,
        BookingStatus.DELAYED,
        BookingStatus.CANCELLED,
        BookingStatus.NO_SHOW,
    },
    BookingStatus.DELAYED: {
        BookingStatus.IN_PROGRESS,
        BookingStatus.ON_MY_WAY,
        BookingStatus.CANCELLED,
        BookingStatus.NO_SHOW,
    },
    BookingStatus.IN_PROGRESS: {BookingStatus.COMPLETED, BookingStatus.CANCELLED},
    BookingStatus.COMPLETED: set(),
    BookingStatus.CANCELLED: set(),
    BookingStatus.NO_SHOW: set(),
}


class PaymentTiming(str, Enum):
    BEFORE_SERVICE = "before_service"
    AFTER_SERVICE = "after_service"
    SPLIT_PAYMENT = "split_payment"


class Booking(Base):
    __tablename__ = "bookings"

    # BookingRepository: check_availability() filters tenant_id+provider_id+status
    # under a row lock on every create; get_bookings_by_customer/_provider filter
    # tenant_id+customer_id/provider_id and ORDER BY scheduled_time. Kept in sync
    # with migration b13compositeidx -- don't let these two drift (bottleneck #17).
    __table_args__ = (
        Index("ix_bookings_tenant_provider_status", "tenant_id", "provider_id", "status"),
        Index("ix_bookings_tenant_customer_scheduled", "tenant_id", "customer_id", "scheduled_time"),
        Index("ix_bookings_tenant_provider_scheduled", "tenant_id", "provider_id", "scheduled_time"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    customer_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"))
    provider_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("providers.id"))
    service_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("services.id"))
    field_agent_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("field_agents.id"), nullable=True)

    # Booking details
    scheduled_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[BookingStatus] = mapped_column(SQLEnum(BookingStatus), default=BookingStatus.PENDING)

    # Location
    location_postcode: Mapped[str] = mapped_column(String(10))
    location_address: Mapped[str] = mapped_column(Text, nullable=True)
    location_coordinates: Mapped[Any] = mapped_column(Geography("POINT", srid=4326, spatial_index=False), nullable=True)

    # Scheduling
    route_order: Mapped[int] = mapped_column(Integer, nullable=True, default=0)

    # Pricing
    base_price_cents: Mapped[int] = mapped_column(Integer)
    deposit_paid_cents: Mapped[int] = mapped_column(Integer, default=0)
    total_paid_cents: Mapped[int] = mapped_column(Integer, default=0)
    payment_timing: Mapped[PaymentTiming] = mapped_column(SQLEnum(PaymentTiming), default=PaymentTiming.BEFORE_SERVICE)
    deposit_percentage: Mapped[int] = mapped_column(Integer, default=0)  # 0-100 for split payments
    promo_code: Mapped[str] = mapped_column(String(50), nullable=True)
    discount_cents: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # Version for optimistic locking — SQLAlchemy auto-increments this and adds a
    # `WHERE version = :old` clause on UPDATE, raising StaleDataError on a concurrent change.
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)

    __mapper_args__ = {"version_id_col": version}

    # Relationships for easier querying (lazy loaded to avoid circular imports)
    customer: Mapped["User"] = relationship("User", foreign_keys=[customer_id], lazy="joined")
    service: Mapped["Service"] = relationship("Service", foreign_keys=[service_id], lazy="joined")
    provider: Mapped["Provider"] = relationship("Provider", foreign_keys=[provider_id], lazy="joined")
    field_agent: Mapped["FieldAgent"] = relationship("FieldAgent", foreign_keys=[field_agent_id], lazy="joined")


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"))
    business_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, nullable=True)
    location: Mapped[Any] = mapped_column(Geography("POINT", srid=4326, spatial_index=False), nullable=True)
    service_radius_km: Mapped[int] = mapped_column(Integer, default=10)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Business details
    business_phone: Mapped[str] = mapped_column(String(20), nullable=True)
    business_email: Mapped[str] = mapped_column(String(255), nullable=True)
    website_url: Mapped[str] = mapped_column(String(500), nullable=True)

    # Ratings
    average_rating: Mapped[float] = mapped_column(Numeric(3, 2), default=0.0)
    total_reviews: Mapped[int] = mapped_column(Integer, default=0)

    # Payment Settings
    payment_timing_default: Mapped[str] = mapped_column(String(20), default="before_service")
    deposit_percentage_default: Mapped[int] = mapped_column(Integer, default=0)
    accepts_cash: Mapped[bool] = mapped_column(Boolean, default=True)
    accepts_card: Mapped[bool] = mapped_column(Boolean, default=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Service(Base):
    __tablename__ = "services"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    provider_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("providers.id"))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, nullable=True)
    service_type: Mapped[str] = mapped_column(String(100))
    base_price_cents: Mapped[int] = mapped_column(Integer)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)

    # Dynamic Pricing
    peak_hour_multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    weekend_multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    min_price_cents: Mapped[int] = mapped_column(Integer, nullable=True)
    max_price_cents: Mapped[int] = mapped_column(Integer, nullable=True)

    # Availability Rules (PG_JSON)
    availability_schedule: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=True)  # {"monday": ["09:00-17:00"], ...}
    blackout_dates: Mapped[List[Any]] = mapped_column(JSONB, nullable=True)  # ["2026-12-25", ...]

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class FieldAgent(Base):
    __tablename__ = "field_agents"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"))
    provider_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("providers.id"))

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)

    # Location tracking
    current_location: Mapped[Any] = mapped_column(Geography("POINT", srid=4326, spatial_index=False), nullable=True)
    last_location_update: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # Skills
    skills: Mapped[List[Any]] = mapped_column(PG_JSON, default=list)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Performance metrics
    average_rating: Mapped[float] = mapped_column(Float, default=0.0)
    total_jobs_completed: Mapped[int] = mapped_column(Integer, default=0)

    # The agent's user account (name/contact for enriched reads) — ORM-only, no migration.
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], lazy="joined")
