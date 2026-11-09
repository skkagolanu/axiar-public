from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.domain.booking.models import Booking, BookingStatus
from app.domain.payment.models import Payment, PaymentStatus
from app.domain.user.models import User, UserRole

router = APIRouter()

from app.api.dependencies.auth import get_current_user


@router.get("/customers")
async def get_customers(session: AsyncSession = Depends(get_db_session), current_user: User = Depends(get_current_user)):
    """Return all customers for the tenant with aggregated spend and last service date."""
    # Single query: customers + spend aggregate + last booking date
    spend_subq = (
        select(
            Booking.customer_id,
            func.sum(Payment.amount_cents).label("total_spend"),
            func.max(Booking.scheduled_time).label("last_service"),
        )
        .join(Payment, Payment.booking_id == Booking.id, isouter=True)
        .where(
            Booking.tenant_id == current_user.tenant_id,
            Booking.status == BookingStatus.COMPLETED,
            Payment.status == PaymentStatus.SUCCEEDED,
        )
        .group_by(Booking.customer_id)
        .subquery()
    )

    query = (
        select(User, spend_subq.c.total_spend, spend_subq.c.last_service)
        .outerjoin(spend_subq, spend_subq.c.customer_id == User.id)
        .where(User.role == UserRole.CUSTOMER, User.tenant_id == current_user.tenant_id)
        .order_by(User.last_name)
    )
    result = await session.execute(query)
    rows = result.all()

    return [
        {
            "id": str(c.id),
            "firstName": c.first_name,
            "lastName": c.last_name,
            "email": c.email,
            "phone": c.phone or "",
            "address": {
                "street": "",
                "city": "",
                "zip": "",
            },
            "tags": [],
            "totalSpend": round((total_spend or 0) / 100, 2),
            "lastServiceDate": last_service.isoformat() if last_service else None,
        }
        for c, total_spend, last_service in rows
    ]


from uuid import uuid4

from pydantic import BaseModel, EmailStr

from app.core.security import security_manager


class CustomerCreate(BaseModel):
    firstName: str
    lastName: str
    email: EmailStr
    phone: str
    address: Optional[dict] = None


@router.post("/customers")
async def create_customer(
    customer: CustomerCreate,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Create a new customer"""
    # Check if exists
    existing = await session.execute(select(User).where(User.email == customer.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = User(
        id=uuid4(),
        tenant_id=current_user.tenant_id,
        email=customer.email,
        # Operator-created customer; sets credentials via invite/magic link, not this password.
        hashed_password=security_manager.generate_unusable_password_hash(),
        first_name=customer.firstName,
        last_name=customer.lastName,
        phone=customer.phone,
        role=UserRole.CUSTOMER,
        is_active=True,
    )
    session.add(new_user)
    await session.commit()

    return {"id": str(new_user.id), "status": "created"}
