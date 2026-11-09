from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user
from app.core.database import get_db_session
from app.domain.booking.models import Booking, BookingStatus, FieldAgent
from app.domain.payment.models import Payment, PaymentStatus
from app.domain.user.models import User

router = APIRouter()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/stats")
async def get_dashboard_stats(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Real-time tenant-scoped dashboard statistics with revenue trend."""
    tenant_id: UUID = current_user.tenant_id
    now = _now_utc()
    cutoff_30 = now - timedelta(days=30)
    cutoff_60 = now - timedelta(days=60)

    # ── Revenue: current vs previous 30-day window in one round-trip ──────────
    revenue_row = (
        await session.execute(
            select(
                func.coalesce(
                    func.sum(case((Payment.created_at >= cutoff_30, Payment.amount_cents), else_=0)),
                    0,
                ).label("current_cents"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(
                                    Payment.created_at >= cutoff_60,
                                    Payment.created_at < cutoff_30,
                                ),
                                Payment.amount_cents,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("previous_cents"),
            ).where(
                and_(
                    Payment.tenant_id == tenant_id,
                    Payment.status == PaymentStatus.SUCCEEDED,
                    Payment.created_at >= cutoff_60,
                )
            )
        )
    ).one()

    current_cents: int = revenue_row.current_cents or 0
    previous_cents: int = revenue_row.previous_cents or 0
    total_revenue = round(current_cents / 100, 2)
    if previous_cents > 0:
        trend_pct = round((current_cents - previous_cents) / previous_cents * 100, 1)
    else:
        trend_pct = 0.0
    trend_direction = "up" if trend_pct >= 0 else "down"

    # ── Bookings: today + in-progress + pending in one round-trip ─────────────
    today_start = datetime.combine(now.date(), datetime.min.time()).replace(tzinfo=timezone.utc)
    today_end = today_start + timedelta(days=1)

    booking_row = (
        await session.execute(
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(
                                    Booking.scheduled_time >= today_start,
                                    Booking.scheduled_time < today_end,
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("today"),
                func.coalesce(
                    func.sum(case((Booking.status == BookingStatus.IN_PROGRESS, 1), else_=0)),
                    0,
                ).label("in_progress"),
                func.coalesce(
                    func.sum(case((Booking.status == BookingStatus.PENDING, 1), else_=0)),
                    0,
                ).label("pending"),
            ).where(Booking.tenant_id == tenant_id)
        )
    ).one()

    # ── Team: active + total in one round-trip ────────────────────────────────
    team_row = (
        await session.execute(
            select(
                func.count(FieldAgent.id).label("total"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(
                                    FieldAgent.is_active == True,  # noqa: E712
                                    FieldAgent.is_available == True,  # noqa: E712
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("active"),
            ).where(FieldAgent.tenant_id == tenant_id)
        )
    ).one()

    return {
        "revenue": {
            "total": total_revenue,
            "trend": abs(trend_pct),
            "trendDirection": trend_direction,
        },
        "jobs": {
            "today": booking_row.today,
            "inProgress": booking_row.in_progress,
            "pending": booking_row.pending,
        },
        "team": {
            "active": team_row.active,
            "total": team_row.total,
        },
    }


@router.get("/activity")
async def get_activity_log(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """Recent activity log — tenant-scoped, newest first, max 20 events."""
    tenant_id: UUID = current_user.tenant_id
    query = select(Booking).where(Booking.tenant_id == tenant_id).order_by(Booking.created_at.desc()).limit(20)
    bookings = (await session.execute(query)).scalars().all()

    def _activity_type(status: BookingStatus) -> str:
        return "job_completed" if status == BookingStatus.COMPLETED else "job_created"

    def _priority(status: BookingStatus) -> str:
        if status == BookingStatus.CANCELLED:
            return "high"
        if status in (BookingStatus.IN_PROGRESS, BookingStatus.ASSIGNED):
            return "medium"
        return "low"

    return [
        {
            "id": str(b.id),
            "type": _activity_type(b.status),
            "message": f"Job {b.status.value}: {b.description or 'Service booking'}",
            "timestamp": b.created_at.isoformat(),
            "priority": _priority(b.status),
        }
        for b in bookings
    ]
