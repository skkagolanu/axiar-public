from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user, require_role
from app.core.database import get_db_session
from app.domain.settings.models import TenantSettings
from app.domain.user.models import User, UserRole

router = APIRouter()


class SettingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    value: str
    description: Optional[str]


class SettingUpsert(BaseModel):
    value: str


@router.get("/", response_model=List[SettingResponse])
async def list_settings(
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db_session),
):
    """Return all settings for the tenant, merging stored values with defaults."""
    result = await db.execute(select(TenantSettings).where(TenantSettings.tenant_id == current_user.tenant_id))
    stored = {s.key: s for s in result.scalars().all()}

    # Merge defaults with stored values
    merged = []
    for key, (default_val, desc) in TenantSettings.DEFAULTS.items():
        if key in stored:
            merged.append({"key": key, "value": stored[key].value, "description": stored[key].description or desc})
        else:
            merged.append({"key": key, "value": default_val, "description": desc})
    # Include any tenant-specific settings not in defaults
    for key, setting in stored.items():
        if key not in TenantSettings.DEFAULTS:
            merged.append({"key": key, "value": setting.value, "description": setting.description})
    return merged


@router.get("/{key}", response_model=SettingResponse)
async def get_setting(
    key: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Return a single setting by key (falls back to default if not set)."""
    result = await db.execute(
        select(TenantSettings).where(TenantSettings.tenant_id == current_user.tenant_id, TenantSettings.key == key)
    )
    setting = result.scalar_one_or_none()
    if setting:
        return {"key": key, "value": setting.value, "description": setting.description}

    if key in TenantSettings.DEFAULTS:
        val, desc = TenantSettings.DEFAULTS[key]
        return {"key": key, "value": val, "description": desc}

    raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")


@router.put("/{key}", response_model=SettingResponse)
async def upsert_setting(
    key: str,
    data: SettingUpsert,
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db_session),
):
    """Create or update a tenant setting (admin only)."""
    result = await db.execute(
        select(TenantSettings).where(TenantSettings.tenant_id == current_user.tenant_id, TenantSettings.key == key)
    )
    setting = result.scalar_one_or_none()
    desc = TenantSettings.DEFAULTS.get(key, (None, None))[1]

    if setting:
        setting.value = data.value
        setting.updated_by = current_user.id
    else:
        setting = TenantSettings(
            tenant_id=current_user.tenant_id,
            key=key,
            value=data.value,
            description=desc,
            updated_by=current_user.id,
        )
        db.add(setting)

    await db.commit()
    await db.refresh(setting)
    return {"key": setting.key, "value": setting.value, "description": setting.description}
