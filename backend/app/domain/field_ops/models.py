"""Field operations domain models"""

from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import Column, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class ExpenseStatus(str, Enum):
    """Expense status enum"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    PAID = "paid"


class Expense(Base):
    """Expense model"""

    __tablename__ = "expenses"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    booking_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bookings.id"))
    field_agent_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("field_agents.id"))

    amount_cents: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    receipt_url: Mapped[str] = mapped_column(String(500), nullable=True)
    status: Mapped[ExpenseStatus] = mapped_column(SQLEnum(ExpenseStatus), default=ExpenseStatus.PENDING)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
