import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import JSON, Boolean, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BookingRule(Base):
    """Auto-acceptance rules for bookings"""

    __tablename__ = "booking_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    provider_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    # Rule configuration
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Conditions (JSON)
    conditions: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    # Example: {"min_advance_hours": 24, "max_bookings_per_day": 5, "allowed_days": [1,2,3,4,5]}

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
