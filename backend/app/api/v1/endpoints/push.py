from typing import Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user
from app.core.cache import cache_manager
from app.core.database import get_db_session
from app.domain.user.models import User
from app.services.push_notification import push_service

router = APIRouter(prefix="/push", tags=["Push Notifications"])

_PUSH_SUB_TTL = 60 * 60 * 24 * 30  # 30 days


class PushSubscription(BaseModel):
    endpoint: str
    keys: Dict[str, str]


@router.post("/subscribe")
async def subscribe_push(
    subscription: PushSubscription,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Subscribe user to push notifications (persisted in Redis)."""
    await cache_manager.set(
        f"push_sub:{current_user.id}",
        {"endpoint": subscription.endpoint, "keys": subscription.keys},
        ttl=_PUSH_SUB_TTL,
    )
    return {"status": "subscribed", "message": "Push notifications enabled"}


@router.post("/test")
async def test_push_notification(subscription: PushSubscription, current_user: User = Depends(get_current_user)):
    """Send test push notification"""
    success = await push_service.send_notification(
        subscription_info=subscription.dict(),
        title="Test Notification",
        body="This is a test notification from Axiar",
        data={"type": "test"},
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to send notification")

    return {"status": "sent", "message": "Test notification sent"}
