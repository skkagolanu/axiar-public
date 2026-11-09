from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class PaymentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class PaymentMethod(str, Enum):
    CARD = "card"
    BANK_TRANSFER = "bank_transfer"
    CASH = "cash"


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    booking_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bookings.id"))

    # Payment details
    amount_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="GBP")
    status: Mapped[PaymentStatus] = mapped_column(SQLEnum(PaymentStatus), default=PaymentStatus.PENDING)
    method: Mapped[PaymentMethod] = mapped_column(SQLEnum(PaymentMethod))

    # Index the external intent identifier used by Stripe callbacks.
    stripe_payment_intent_id: Mapped[str] = mapped_column(String(255), nullable=True, index=True)
    stripe_charge_id: Mapped[str] = mapped_column(String(255), nullable=True)
    external_transaction_id: Mapped[str] = mapped_column(String(255), nullable=True)

    # Metadata
    payment_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    failure_reason: Mapped[str] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)


class Refund(Base):
    __tablename__ = "refunds"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    payment_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("payments.id"))

    # Refund details
    amount_cents: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[PaymentStatus] = mapped_column(SQLEnum(PaymentStatus), default=PaymentStatus.PENDING)

    # External refund details
    stripe_refund_id: Mapped[str] = mapped_column(String(255), nullable=True)
    external_refund_id: Mapped[str] = mapped_column(String(255), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
