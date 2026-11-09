from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EmailCampaignCreate(BaseModel):
    name: str
    subject: str
    body: str
    segment: str | None = "all"
    scheduled_at: datetime | None = None


class EmailCampaignResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    subject: str
    body: str
    segment: str | None
    status: str
    sent_count: int
    opened_count: int
    clicked_count: int
    scheduled_at: datetime | None
    sent_at: datetime | None
    created_at: datetime
