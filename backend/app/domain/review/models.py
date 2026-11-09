"""Review domain models"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class Review(Base):
    """Review model"""

    __tablename__ = "reviews"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    booking_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bookings.id"))
    customer_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    provider_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("providers.id"))

    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
