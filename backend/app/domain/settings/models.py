from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class TenantSettings(Base):
    """Key-value configuration per tenant. String values; callers cast as needed."""

    __tablename__ = "tenant_settings"
    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_tenant_settings_tenant_key"),)

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=True)
    updated_by: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Sensible defaults (upserted at runtime)
    DEFAULTS: dict = {
        "commission_pct": ("5", "Platform commission percentage applied to each completed booking"),
        "late_threshold_minutes": ("15", "Minutes after scheduled start before a booking is considered late"),
        "max_bookings_per_day": ("20", "Maximum bookings a provider can accept per day"),
        "currency": ("GBP", "Currency code used on all invoices"),
    }
