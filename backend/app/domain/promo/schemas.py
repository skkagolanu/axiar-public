from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DiscountType(str, Enum):
    PERCENTAGE = "percentage"
    FIXED_AMOUNT = "fixed_amount"


class PromoCodeCreate(BaseModel):
    code: str = Field(..., min_length=3, max_length=50)
    discount_type: DiscountType
    discount_value: int = Field(..., ge=1)
    max_uses: int | None = None
    min_purchase_cents: int = Field(default=0, ge=0)
    valid_from: datetime
    valid_until: datetime


class PromoCodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    discount_type: DiscountType
    discount_value: int
    max_uses: int | None
    current_uses: int
    min_purchase_cents: int
    valid_from: datetime
    valid_until: datetime
    is_active: bool


class PromoCodeValidation(BaseModel):
    code: str
    booking_amount_cents: int


class PromoCodeValidationResponse(BaseModel):
    valid: bool
    discount_cents: int
    message: str
