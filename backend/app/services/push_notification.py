import json
import logging
from typing import Any, Dict, Optional

from pywebpush import WebPushException, webpush

from app.core.config import settings

logger = logging.getLogger(__name__)


class PushNotificationService:
    """Web Push Notifications service"""

    def __init__(self):
        self.vapid_private_key = settings.VAPID_PRIVATE_KEY
        self.vapid_public_key = settings.VAPID_PUBLIC_KEY
        self.vapid_claims = {"sub": settings.VAPID_SUBJECT}
        self.subscriptions = {}  # In-memory storage for testing

    async def subscribe(self, user_id: int, subscription: Dict[str, Any]) -> Dict[str, Any]:
        """Subscribe user to push notifications"""
        self.subscriptions[user_id] = subscription
        return {"success": True, "message": "Subscribed successfully"}

    async def unsubscribe(self, user_id: int) -> Dict[str, Any]:
        """Unsubscribe user from push notifications"""
        if user_id in self.subscriptions:
            del self.subscriptions[user_id]
            return {"success": True, "message": "Unsubscribed successfully"}
        return {"success": False, "message": "Subscription not found"}

    def _is_real_vapid_key(self) -> bool:
        """Return True only when a non-placeholder VAPID private key is configured."""
        if not self.vapid_private_key:
            return False
        key = str(self.vapid_private_key).strip()
        # Common placeholder / obviously-invalid values should degrade to mock mode.
        if key.lower() in {"", "changeme", "change", "mock", "none", "null"}:
            return False
        # A real base64url-encoded VAPID private key is much longer than this.
        return len(key) >= 20

    async def send_notification(
        self,
        subscription_info: Dict[str, Any] = None,
        title: str = "",
        body: str = "",
        data: Optional[Dict[str, Any]] = None,
        user_id: int = None,
    ) -> Dict[str, Any]:
        """Send push notification to a subscription"""
        # Support both direct subscription_info and user_id lookup
        if user_id is not None:
            subscription_info = self.subscriptions.get(user_id)
            if not subscription_info:
                return {"success": False, "error": "No subscription found"}

        if not subscription_info:
            return {"success": False, "error": "No subscription provided"}

        if not self._is_real_vapid_key():
            logger.info(f"Mock: Push notification - {title}: {body}")
            return {"success": True, "message": "Notification sent (mock mode)", "mode": "mock"}

        try:
            payload = json.dumps({"title": title, "body": body, "data": data or {}})

            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=self.vapid_private_key,
                vapid_claims=self.vapid_claims,
            )

            logger.info(f"Push notification sent: {title}")
            return {"success": True, "message": "Notification sent"}

        except WebPushException as e:
            logger.error(f"Push notification failed: {e}")
            return {"success": False, "error": str(e)}

    async def send_booking_update(self, subscription_info: Dict[str, Any], booking_id: str, status: str) -> Dict[str, Any]:
        """Send booking status update notification"""
        return await self.send_notification(
            subscription_info=subscription_info,
            title="Booking Update",
            body=f"Your booking status changed to: {status}",
            data={"booking_id": booking_id, "status": status, "type": "booking_update"},
        )

    async def send_job_assignment(self, subscription_info: Dict[str, Any], job_id: str, job_title: str) -> Dict[str, Any]:
        """Send job assignment notification to field agent"""
        return await self.send_notification(
            subscription_info=subscription_info,
            title="New Job Assigned",
            body=f"You have been assigned: {job_title}",
            data={"job_id": job_id, "type": "job_assignment"},
        )


push_service = PushNotificationService()
