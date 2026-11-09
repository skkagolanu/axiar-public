from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class Referral(Base):
    __tablename__ = "referrals"
    __table_args__ = (
        Index("idx_referrals_referrer", "referrer_id"),
        Index("idx_referrals_referred", "referred_id"),
        Index("idx_referrals_code", "referral_code"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    referrer_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    referred_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    referral_code: Mapped[str] = mapped_column(String(20))
    reward_cents: Mapped[int] = mapped_column(Integer, default=0)
    is_rewarded: Mapped[bool] = mapped_column(Boolean, default=False)
    tenant_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
