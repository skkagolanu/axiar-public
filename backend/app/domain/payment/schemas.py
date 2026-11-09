from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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


class PaymentCreate(BaseModel):
    booking_id: UUID
    amount_cents: int = Field(..., ge=100)
    method: PaymentMethod = PaymentMethod.CARD
    metadata: Optional[Dict[str, Any]] = None


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    booking_id: UUID
    amount_cents: int
    currency: str
    status: PaymentStatus
    method: PaymentMethod
    stripe_payment_intent_id: Optional[str]
    created_at: datetime
    processed_at: Optional[datetime]


PaymentResponse = PaymentRead


class PaymentIntentResponse(BaseModel):
    client_secret: str
    payment_id: UUID


class RefundCreate(BaseModel):
    payment_id: UUID
    amount_cents: Optional[int] = None  # Full refund if None
    reason: Optional[str] = None


class RefundRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    payment_id: UUID
    amount_cents: int
    reason: Optional[str]
    status: PaymentStatus
    created_at: datetime
    processed_at: Optional[datetime]
