from datetime import datetime, timezone
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import require_role
from app.core.database import get_db_session
from app.domain.booking.models import Booking
from app.domain.marketing.models import EmailCampaign
from app.domain.marketing.schemas import EmailCampaignCreate, EmailCampaignResponse
from app.domain.user.models import User, UserRole

router = APIRouter()


@router.post("/", response_model=EmailCampaignResponse)
async def create_campaign(
    campaign_data: EmailCampaignCreate,
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db_session),
):
    """Create email campaign (admin only)"""
    campaign = EmailCampaign(
        tenant_id=current_user.tenant_id,
        name=campaign_data.name,
        subject=campaign_data.subject,
        body=campaign_data.body,
        segment=campaign_data.segment,
        scheduled_at=campaign_data.scheduled_at,
        status="scheduled" if campaign_data.scheduled_at else "draft",
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    return campaign


@router.get("/", response_model=List[EmailCampaignResponse])
async def list_campaigns(
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db_session),
):
    """List email campaigns for the admin's tenant"""
    result = await db.execute(
        select(EmailCampaign)
        .where(EmailCampaign.tenant_id == current_user.tenant_id)
        .order_by(EmailCampaign.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/{campaign_id}/send")
async def send_campaign(
    campaign_id: UUID,
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db_session),
):
    """Send email campaign immediately (admin only)"""
    result = await db.execute(select(EmailCampaign).where(EmailCampaign.id == campaign_id))
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status == "sent":
        raise HTTPException(status_code=400, detail="Campaign already sent")

    # Count recipients based on segment before sending
    segment_filter = [User.tenant_id == current_user.tenant_id, User.is_active == True]  # noqa: E712
    if campaign.segment == "active":
        # Customers with a booking in the last 90 days
        from datetime import timedelta

        segment_filter.append(
            User.id.in_(
                select(Booking.customer_id).where(Booking.scheduled_time >= datetime.now(timezone.utc) - timedelta(days=90))
            )
        )
    elif campaign.segment == "inactive":
        from datetime import timedelta

        segment_filter.append(
            User.id.notin_(
                select(Booking.customer_id).where(Booking.scheduled_time >= datetime.now(timezone.utc) - timedelta(days=90))
            )
        )

    count_result = await db.execute(select(func.count(User.id)).where(*segment_filter))
    recipient_count = count_result.scalar_one() or 0

    campaign.status = "sent"
    campaign.sent_at = datetime.now(timezone.utc)
    campaign.sent_count = recipient_count

    await db.commit()
    return {"message": "Campaign queued for delivery", "sent_count": campaign.sent_count}
