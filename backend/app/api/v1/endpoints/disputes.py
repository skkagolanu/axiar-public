from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user, require_role
from app.core.database import get_db_session
from app.domain.dispute.models import Dispute, DisputeReason, DisputeStatus
from app.domain.user.models import User, UserRole

router = APIRouter()


class DisputeCreate(BaseModel):
    booking_id: UUID
    reason: DisputeReason
    description: str
    evidence_urls: Optional[List[str]] = None


class DisputeResolve(BaseModel):
    resolution_notes: str
    status: DisputeStatus = DisputeStatus.RESOLVED


class DisputeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    booking_id: UUID
    raised_by: UUID
    reason: str
    description: str
    status: str
    resolution_notes: Optional[str]
    created_at: datetime
    resolved_at: Optional[datetime]


@router.post("/", response_model=DisputeResponse, status_code=201)
async def open_dispute(
    data: DisputeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Open a dispute for a booking (customer or provider)."""
    dispute = Dispute(
        tenant_id=current_user.tenant_id,
        booking_id=data.booking_id,
        raised_by=current_user.id,
        reason=data.reason.value,
        description=data.description,
        evidence_urls=",".join(data.evidence_urls) if data.evidence_urls else None,
        status=DisputeStatus.OPEN.value,
    )
    db.add(dispute)
    await db.commit()
    await db.refresh(dispute)
    return dispute


@router.get("/", response_model=List[DisputeResponse])
async def list_disputes(
    status: Optional[str] = None,
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db_session),
):
    """List all disputes for the tenant (admin only)."""
    query = select(Dispute).where(Dispute.tenant_id == current_user.tenant_id).order_by(Dispute.created_at.desc())
    if status:
        query = query.where(Dispute.status == status)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/my", response_model=List[DisputeResponse])
async def list_my_disputes(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """List disputes raised by the current user."""
    result = await db.execute(select(Dispute).where(Dispute.raised_by == current_user.id).order_by(Dispute.created_at.desc()))
    return list(result.scalars().all())


@router.get("/{dispute_id}", response_model=DisputeResponse)
async def get_dispute(
    dispute_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get a single dispute by ID."""
    dispute = (await db.execute(select(Dispute).where(Dispute.id == dispute_id))).scalar_one_or_none()
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")
    if dispute.raised_by != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Access denied")
    return dispute


@router.patch("/{dispute_id}/resolve", response_model=DisputeResponse)
async def resolve_dispute(
    dispute_id: UUID,
    data: DisputeResolve,
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db_session),
):
    """Resolve or close a dispute (admin only)."""
    dispute = (await db.execute(select(Dispute).where(Dispute.id == dispute_id))).scalar_one_or_none()
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")

    dispute.status = data.status.value
    dispute.resolution_notes = data.resolution_notes
    dispute.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(dispute)
    return dispute
