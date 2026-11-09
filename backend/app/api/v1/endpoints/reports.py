from datetime import date, datetime, timedelta
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.domain.booking.models import Booking, BookingStatus, FieldAgent
from app.domain.payment.models import Payment, PaymentStatus
from app.domain.user.models import User

router = APIRouter()

from app.api.dependencies.auth import get_current_user


@router.get("/revenue")
async def get_revenue_report(session: AsyncSession = Depends(get_db_session), current_user: User = Depends(get_current_user)):
    """Get daily revenue for the last 30 days"""
    today = date.today()
    start_date = today - timedelta(days=30)

    # Optimized SQL aggregation
    query = (
        select(func.date(Payment.created_at).label("date"), func.sum(Payment.amount_cents).label("total"))
        .where(
            Payment.status == PaymentStatus.SUCCEEDED,
            Payment.created_at >= datetime.combine(start_date, datetime.min.time()),
            Payment.tenant_id == current_user.tenant_id,
        )
        .group_by(func.date(Payment.created_at))
        .order_by(func.date(Payment.created_at))
    )

    result = await session.execute(query)
    rows = result.all()

    # Map to dictionary for easy lookup
    revenue_map = {r.date.isoformat(): r.total / 100 for r in rows if r.date}

    # Fill gaps
    chart_data = []
    for i in range(31):
        d = (start_date + timedelta(days=i)).isoformat()
        amount = revenue_map.get(d, 0)
        chart_data.append({"date": d, "amount": amount})

    return chart_data


@router.get("/tech-performance")
async def get_tech_performance(
    session: AsyncSession = Depends(get_db_session), current_user: User = Depends(get_current_user)
):
    """Get technician completion rates (single grouped aggregate — no per-agent N+1)."""
    completed_count = func.count(case((Booking.status == BookingStatus.COMPLETED, Booking.id)))
    total_count = func.count(Booking.id)

    query = (
        select(
            User.first_name,
            User.last_name,
            completed_count.label("completed"),
            total_count.label("total"),
        )
        .select_from(FieldAgent)
        .join(User, FieldAgent.user_id == User.id)
        .outerjoin(Booking, Booking.field_agent_id == FieldAgent.id)
        .where(User.tenant_id == current_user.tenant_id)
        .group_by(FieldAgent.id, User.first_name, User.last_name)
    )
    result = await session.execute(query)

    return [
        {
            "name": f"{row.first_name} {row.last_name}".strip(),
            "completed": row.completed or 0,
            "total": row.total or 0,
            "delayed": 0,
        }
        for row in result
    ]
