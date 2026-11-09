import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PaymentScheduleBase(BaseModel):
    milestone_name: str
    amount_cents: int
    due_date: datetime


class PaymentScheduleCreate(PaymentScheduleBase):
    pass


class PaymentScheduleRead(PaymentScheduleBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    booking_id: uuid.UUID
    status: str
    payment_id: uuid.UUID | None = None
    paid_at: datetime | None = None
    created_at: datetime


class CreateScheduleRequest(BaseModel):
    booking_id: uuid.UUID
    milestones: list[dict]
