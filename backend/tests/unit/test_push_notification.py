"""Unit tests for push notification service."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from app.services.push_notification import PushNotificationService


@pytest.fixture
def push_service():
    return PushNotificationService()


@pytest.mark.asyncio
async def test_subscribe_success(push_service):
    """Test successful subscription."""
    subscription = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/test",
        "keys": {"p256dh": "test_key", "auth": "test_auth"},
    }

    result = await push_service.subscribe(user_id=1, subscription=subscription)

    assert result["success"] is True
    assert 1 in push_service.subscriptions
    assert push_service.subscriptions[1] == subscription


@pytest.mark.asyncio
async def test_send_notification_with_vapid(push_service):
    """Test sending notification with VAPID keys."""
    push_service.vapid_private_key = "test_private_key_long_enough_for_vapid"
    push_service.vapid_claims = {"sub": "mailto:test@example.com"}
    push_service.subscriptions[1] = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/test",
        "keys": {"p256dh": "test_key", "auth": "test_auth"},
    }

    with patch("app.services.push_notification.webpush") as mock_webpush:
        mock_webpush.return_value = MagicMock(status_code=201)

        result = await push_service.send_notification(user_id=1, title="Test", body="Test message", data={"action": "test"})

        assert result["success"] is True
        mock_webpush.assert_called_once()


@pytest.mark.asyncio
async def test_send_notification_no_vapid(push_service):
    """Test notification without VAPID keys (mock mode)."""
    push_service.subscriptions[1] = {"endpoint": "test"}

    result = await push_service.send_notification(user_id=1, title="Test", body="Test message")

    assert result["success"] is True
    assert result["mode"] == "mock"


@pytest.mark.asyncio
async def test_send_notification_no_subscription(push_service):
    """Test notification with no subscription."""
    result = await push_service.send_notification(user_id=999, title="Test", body="Test")

    assert result["success"] is False
    assert "No subscription" in result["error"]


@pytest.mark.asyncio
async def test_unsubscribe(push_service):
    """Test unsubscribe."""
    push_service.subscriptions[1] = {"endpoint": "test"}

    result = await push_service.unsubscribe(user_id=1)

    assert result["success"] is True
    assert 1 not in push_service.subscriptions
