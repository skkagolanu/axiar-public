import uuid
from datetime import datetime
from typing import Any, Dict

from pydantic import BaseModel, ConfigDict, field_validator


class TenantBase(BaseModel):
    name: str
    slug: str
    settings: Dict[str, Any] = {}


class TenantCreate(TenantBase):
    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Slug must contain only alphanumeric characters, hyphens, and underscores")
        return v.lower()


class TenantUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None
    settings: Dict[str, Any] | None = None


class TenantRead(TenantBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
