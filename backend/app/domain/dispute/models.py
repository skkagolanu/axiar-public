from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class DisputeStatus(str, Enum):
    OPEN = "open"
    UNDER_REVIEW = "under_review"
    RESOLVED = "resolved"
    CLOSED = "closed"


class DisputeReason(str, Enum):
    SERVICE_NOT_RENDERED = "service_not_rendered"
    QUALITY_ISSUE = "quality_issue"
    OVERCHARGE = "overcharge"
    NO_SHOW_PROVIDER = "no_show_provider"
    OTHER = "other"


class Dispute(Base):
    __tablename__ = "disputes"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    booking_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=False, index=True)
    raised_by: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    assigned_to: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    reason: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text)
    evidence_urls: Mapped[str] = mapped_column(Text, nullable=True)  # comma-separated URLs
    status: Mapped[str] = mapped_column(String(20), default=DisputeStatus.OPEN.value, index=True)
    resolution_notes: Mapped[str] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
