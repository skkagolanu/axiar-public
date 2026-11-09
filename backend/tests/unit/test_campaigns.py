"""
Unit tests for email campaigns

"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.domain.marketing.models import EmailCampaign


@pytest.mark.asyncio
async def test_create_email_campaign(db_session):
    """Test creating an email campaign"""
    campaign = EmailCampaign(
        name="Welcome Campaign",
        subject="Welcome to Axiar!",
        body="Thank you for joining us.",
        segment="all",
        status="draft",
    )
    db_session.add(campaign)
    await db_session.commit()

    assert campaign.name == "Welcome Campaign"
    assert campaign.status == "draft"
    assert campaign.sent_count == 0


@pytest.mark.asyncio
async def test_schedule_campaign(db_session):
    """Test scheduling a campaign"""
    scheduled_time = datetime.now(timezone.utc) + timedelta(days=1)

    campaign = EmailCampaign(
        name="Scheduled Campaign",
        subject="Special Offer",
        body="Limited time offer!",
        segment="active",
        status="scheduled",
        scheduled_at=scheduled_time,
    )
    db_session.add(campaign)
    await db_session.commit()

    assert campaign.status == "scheduled"
    assert campaign.scheduled_at == scheduled_time
    assert campaign.sent_at is None


@pytest.mark.asyncio
async def test_send_campaign(db_session):
    """Test sending a campaign"""
    campaign = EmailCampaign(
        name="Send Test",
        subject="Test Email",
        body="Test body",
        segment="all",
        status="draft",
    )
    db_session.add(campaign)
    await db_session.commit()

    # Simulate sending
    campaign.status = "sent"
    campaign.sent_at = datetime.now(timezone.utc)
    campaign.sent_count = 100
    await db_session.commit()

    assert campaign.status == "sent"
    assert campaign.sent_at is not None
    assert campaign.sent_count == 100


@pytest.mark.asyncio
async def test_campaign_metrics(db_session):
    """Test campaign metrics tracking"""
    campaign = EmailCampaign(
        name="Metrics Test",
        subject="Track This",
        body="Body text",
        segment="all",
        status="sent",
        sent_count=1000,
        opened_count=0,
        clicked_count=0,
    )
    db_session.add(campaign)
    await db_session.commit()

    # Simulate opens and clicks
    campaign.opened_count = 450
    campaign.clicked_count = 120
    await db_session.commit()

    assert campaign.opened_count == 450
    assert campaign.clicked_count == 120
    assert campaign.opened_count / campaign.sent_count == 0.45  # 45% open rate


@pytest.mark.asyncio
async def test_list_campaigns(db_session):
    """Test listing campaigns"""
    # Create multiple campaigns
    for i in range(5):
        campaign = EmailCampaign(
            name=f"Campaign {i}",
            subject=f"Subject {i}",
            body=f"Body {i}",
            segment="all",
            status="draft" if i % 2 == 0 else "sent",
        )
        db_session.add(campaign)

    await db_session.commit()

    result = await db_session.execute(select(EmailCampaign))
    campaigns = list(result.scalars().all())

    assert len(campaigns) >= 5


@pytest.mark.asyncio
async def test_campaign_segmentation(db_session):
    """Test campaign segmentation"""
    segments = ["all", "active", "inactive", "new"]

    for segment in segments:
        campaign = EmailCampaign(
            name=f"{segment.title()} Campaign",
            subject=f"For {segment} users",
            body="Targeted content",
            segment=segment,
            status="draft",
        )
        db_session.add(campaign)

    await db_session.commit()

    result = await db_session.execute(select(EmailCampaign).where(EmailCampaign.segment == "active"))
    active_campaigns = list(result.scalars().all())

    assert len(active_campaigns) >= 1
    assert all(c.segment == "active" for c in active_campaigns)
