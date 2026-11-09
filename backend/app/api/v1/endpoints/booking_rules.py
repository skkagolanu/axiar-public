from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user, require_role
from app.core.database import get_db_session
from app.domain.booking_rules.repository import BookingRuleRepository
from app.domain.user.models import User, UserRole

router = APIRouter()


class RuleCreate(BaseModel):
    provider_id: UUID
    name: str
    conditions: dict
    priority: int = 0


class RuleUpdate(BaseModel):
    name: str | None = None
    conditions: dict | None = None
    priority: int | None = None
    is_active: bool | None = None


@router.post("/rules", response_model=Dict[str, Any])
async def create_rule(
    rule: RuleCreate,
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.PROVIDER])),
    session: AsyncSession = Depends(get_db_session),
):
    """Create auto-acceptance rule"""
    repo = BookingRuleRepository(session)
    created_rule = await repo.create(
        provider_id=rule.provider_id,
        name=rule.name,
        conditions=rule.conditions,
        priority=rule.priority,
    )
    await session.commit()
    return {
        "id": str(created_rule.id),
        "provider_id": str(created_rule.provider_id),
        "name": created_rule.name,
        "conditions": created_rule.conditions,
        "priority": created_rule.priority,
        "is_active": created_rule.is_active,
    }


@router.get("/rules/provider/{provider_id}", response_model=Dict[str, Any])
async def get_provider_rules(
    provider_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Get rules for provider"""
    repo = BookingRuleRepository(session)
    rules = await repo.get_by_provider(provider_id)
    return {
        "provider_id": str(provider_id),
        "rules": [
            {
                "id": str(rule.id),
                "name": rule.name,
                "conditions": rule.conditions,
                "priority": rule.priority,
                "is_active": rule.is_active,
            }
            for rule in rules
        ],
    }


@router.patch("/rules/{rule_id}", response_model=Dict[str, Any])
async def update_rule(
    rule_id: UUID,
    updates: RuleUpdate,
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.PROVIDER])),
    session: AsyncSession = Depends(get_db_session),
):
    """Update rule"""
    repo = BookingRuleRepository(session)
    updated_rule = await repo.update(rule_id, **updates.model_dump(exclude_unset=True))
    await session.commit()
    return {
        "id": str(updated_rule.id),
        "provider_id": str(updated_rule.provider_id),
        "name": updated_rule.name,
        "conditions": updated_rule.conditions,
        "priority": updated_rule.priority,
        "is_active": updated_rule.is_active,
    }
