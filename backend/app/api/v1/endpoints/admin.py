from datetime import date
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import require_role
from app.core.database import get_db_session
from app.domain.booking.models import Booking, BookingStatus, FieldAgent, Provider
from app.domain.booking.schemas import ProviderRead
from app.domain.payment.models import Payment, PaymentStatus
from app.domain.user.models import User, UserRole

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/users", response_model=Dict[str, Any])
async def list_users(
    skip: int = Query(0, ge=0, le=1_000_000),
    limit: int = Query(100, ge=1, le=500),
    role: Optional[UserRole] = None,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db_session),
):
    """List users in the admin's tenant with pagination"""
    query = select(User).where(User.tenant_id == current_user.tenant_id).offset(skip).limit(limit)
    if role:
        query = query.where(User.role == role)

    result = await db.execute(query)
    users = result.scalars().all()
    return {
        "users": [
            {
                "id": str(u.id),
                "email": u.email,
                "role": u.role.value,
                "is_active": u.is_active,
                "is_verified": u.is_verified,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ],
        "total": len(users),
    }


@router.patch("/users/{user_id}/status", response_model=Dict[str, Any])
async def update_user_status(
    user_id: UUID,
    is_active: bool,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db_session),
):
    """Activate or deactivate user"""
    result = await db.execute(select(User).where(User.id == user_id, User.tenant_id == current_user.tenant_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = is_active
    await db.commit()

    return {"status": "updated", "user_id": str(user_id), "is_active": is_active}


@router.get("/analytics/revenue", response_model=List[Dict[str, Any]])
async def get_revenue_analytics(
    start_date: date,
    end_date: date,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db_session),
):
    """Get revenue analytics by date"""
    query = (
        select(
            func.date(Booking.created_at).label("date"),
            func.sum(Booking.base_price_cents).label("revenue"),
            func.count(Booking.id).label("bookings"),
        )
        .where(
            and_(
                Booking.tenant_id == current_user.tenant_id,
                Booking.status == BookingStatus.COMPLETED,
                func.date(Booking.created_at).between(start_date, end_date),
            )
        )
        .group_by(func.date(Booking.created_at))
    )

    result = await db.execute(query)
    return [{"date": str(row.date), "revenue_gbp": (row.revenue or 0) / 100, "bookings": row.bookings} for row in result]


@router.get("/analytics/overview", response_model=Dict[str, Any])
async def get_system_overview(current_user: User = Depends(require_role("admin")), db: AsyncSession = Depends(get_db_session)):
    """Get system overview statistics for the admin's tenant"""
    tid = current_user.tenant_id
    total_users = await db.execute(select(func.count(User.id)).where(User.tenant_id == tid))
    total_bookings = await db.execute(select(func.count(Booking.id)).where(Booking.tenant_id == tid))
    total_revenue = await db.execute(
        select(func.sum(Booking.base_price_cents)).where(Booking.tenant_id == tid, Booking.status == BookingStatus.COMPLETED)
    )

    return {
        "total_users": total_users.scalar() or 0,
        "total_bookings": total_bookings.scalar() or 0,
        "total_revenue_gbp": (total_revenue.scalar() or 0) / 100,
        "status": "operational",
    }


@router.get("/providers/pending", response_model=List[ProviderRead])
async def list_pending_providers(
    current_user: User = Depends(require_role("admin")), db: AsyncSession = Depends(get_db_session)
):
    """List providers pending approval"""
    result = await db.execute(
        select(Provider).where(Provider.is_active == False, Provider.tenant_id == current_user.tenant_id)  # noqa: E712
    )
    return result.scalars().all()


@router.get("/payments/failed", response_model=Dict[str, Any])
async def list_failed_payments(
    skip: int = Query(0, ge=0, le=1_000_000),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db_session),
):
    """List failed payments for the tenant with booking context."""
    result = await db.execute(
        select(Payment, Booking.id.label("booking_id"))
        .join(Booking, Payment.booking_id == Booking.id)
        .where(Payment.status == PaymentStatus.FAILED, Booking.tenant_id == current_user.tenant_id)
        .order_by(Payment.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    rows = result.all()
    return {
        "failed_payments": [
            {
                "id": str(p.id),
                "booking_id": str(p.booking_id),
                "amount_gbp": (p.amount_cents or 0) / 100,
                "stripe_payment_intent_id": p.stripe_payment_intent_id,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "metadata": p.metadata or {},
            }
            for p, _ in rows
        ],
        "total": len(rows),
    }


@router.get("/providers/status", response_model=Dict[str, Any])
async def provider_status_breakdown(
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db_session),
):
    """Active vs pending provider counts + active field agent count."""
    active_count = (
        await db.execute(
            select(func.count(Provider.id)).where(
                Provider.tenant_id == current_user.tenant_id, Provider.is_active == True
            )  # noqa: E712
        )
    ).scalar() or 0

    pending_count = (
        await db.execute(
            select(func.count(Provider.id)).where(
                Provider.tenant_id == current_user.tenant_id, Provider.is_active == False
            )  # noqa: E712
        )
    ).scalar() or 0

    active_agents = (
        await db.execute(
            select(func.count(FieldAgent.id)).where(
                FieldAgent.tenant_id == current_user.tenant_id, FieldAgent.is_active == True  # noqa: E712
            )
        )
    ).scalar() or 0

    return {
        "providers": {"active": active_count, "pending": pending_count, "total": active_count + pending_count},
        "field_agents": {"active": active_agents},
    }


@router.patch("/providers/{provider_id}/approve", response_model=Dict[str, Any])
async def approve_provider(
    provider_id: UUID,
    approved: bool,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db_session),
):
    """Approve or reject provider"""
    result = await db.execute(select(Provider).where(Provider.id == provider_id, Provider.tenant_id == current_user.tenant_id))
    provider = result.scalar_one_or_none()

    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    provider.is_active = approved
    await db.commit()

    return {"status": "updated", "provider_id": str(provider_id), "approved": approved}
