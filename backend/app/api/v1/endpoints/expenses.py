from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user, require_role
from app.core.database import get_db_session
from app.domain.booking.models import FieldAgent
from app.domain.field_ops.models import Expense, ExpenseStatus
from app.domain.user.models import User, UserRole

router = APIRouter()


async def _get_current_field_agent(db: AsyncSession, current_user: User) -> FieldAgent:
    """Resolve the caller's own FieldAgent row. field_agent_id columns are a FieldAgent.id
    (its own PK), never the caller's User.id -- every query/write against them must go
    through here rather than comparing against current_user.id directly."""
    result = await db.execute(
        select(FieldAgent).where(FieldAgent.user_id == current_user.id, FieldAgent.tenant_id == current_user.tenant_id)
    )
    field_agent = result.scalar_one_or_none()
    if not field_agent:
        raise HTTPException(status_code=404, detail="Field agent profile not found")
    return field_agent


class ExpenseCreate(BaseModel):
    booking_id: UUID
    amount_cents: int = Field(..., ge=1)
    category: str
    description: str
    receipt_url: Optional[str] = None


class ExpenseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    booking_id: UUID
    field_agent_id: UUID
    amount_cents: int
    category: str
    description: str
    status: ExpenseStatus
    created_at: datetime


@router.get("/", response_model=List[ExpenseResponse])
async def list_expenses(
    skip: int = Query(0, ge=0, le=1_000_000),
    limit: int = Query(100, ge=1, le=500),
    status: Optional[ExpenseStatus] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """List expenses for the caller's tenant, optionally filtered by status"""
    query = (
        select(Expense)
        .where(Expense.tenant_id == current_user.tenant_id)
        .offset(skip)
        .limit(limit)
        .order_by(Expense.created_at.desc())
    )

    if status:
        query = query.where(Expense.status == status)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.post("/", response_model=ExpenseResponse, status_code=status.HTTP_201_CREATED)
async def create_expense(
    expense_data: ExpenseCreate,
    current_user: User = Depends(require_role([UserRole.FIELD_AGENT])),
    db: AsyncSession = Depends(get_db_session),
):
    """Create expense claim"""
    field_agent = await _get_current_field_agent(db, current_user)

    expense = Expense(
        tenant_id=current_user.tenant_id,
        booking_id=expense_data.booking_id,
        field_agent_id=field_agent.id,
        amount_cents=expense_data.amount_cents,
        category=expense_data.category,
        description=expense_data.description,
        receipt_url=expense_data.receipt_url,
        status=ExpenseStatus.PENDING,
    )
    db.add(expense)
    await db.commit()
    await db.refresh(expense)
    return expense


@router.get("/my-expenses", response_model=List[ExpenseResponse])
async def get_my_expenses(
    current_user: User = Depends(require_role([UserRole.FIELD_AGENT])),
    db: AsyncSession = Depends(get_db_session),
):
    """Get field agent's expenses"""
    field_agent = await _get_current_field_agent(db, current_user)
    result = await db.execute(
        select(Expense).where(Expense.field_agent_id == field_agent.id).order_by(Expense.created_at.desc())
    )
    return list(result.scalars().all())


@router.patch("/{expense_id}/approve", response_model=ExpenseResponse)
async def approve_expense(
    expense_id: UUID,
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.PROVIDER])),
    db: AsyncSession = Depends(get_db_session),
):
    """Approve expense claim (tenant-scoped)"""
    result = await db.execute(select(Expense).where(Expense.id == expense_id, Expense.tenant_id == current_user.tenant_id))
    expense = result.scalar_one_or_none()

    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    expense.status = ExpenseStatus.APPROVED
    await db.commit()
    await db.refresh(expense)
    return expense
