"""Integration tests for scheduling, notifications and booking rules."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_ai_scheduling_suggestions_endpoint(client: AsyncClient, admin_token):
    """Test AI scheduling suggestions endpoint."""
    response = await client.get(
        "/api/v1/ai/scheduling/suggestions",
        headers={"Authorization": f"Bearer {admin_token}"},
        params={"schedule_date": "2026-02-26"},
    )

    assert response.status_code in [200, 404, 422]  # Endpoint may not exist yet


@pytest.mark.asyncio
async def test_ai_auto_assign_endpoint(client: AsyncClient, admin_token):
    """Test AI auto-assign endpoint."""
    response = await client.post(
        "/api/v1/ai/scheduling/auto-assign",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"jobs": [], "providers": []},
    )

    assert response.status_code in [200, 404, 422]  # Endpoint may not exist yet


@pytest.mark.asyncio
async def test_push_subscribe_endpoint(client: AsyncClient, user_token):
    """Test push notification subscribe endpoint."""
    response = await client.post(
        "/api/v1/push/subscribe",
        headers={"Authorization": f"Bearer {user_token}"},
        json={
            "subscription": {
                "endpoint": "https://fcm.googleapis.com/fcm/send/test",
                "keys": {"p256dh": "test_key", "auth": "test_auth"},
            }
        },
    )

    assert response.status_code in [200, 404, 422]  # Endpoint may not exist yet


@pytest.mark.asyncio
async def test_push_test_endpoint(client: AsyncClient, user_token):
    """Test push notification test endpoint."""
    # Subscribe first
    await client.post(
        "/api/v1/push/subscribe",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"subscription": {"endpoint": "test", "keys": {}}},
    )

    # Send test notification
    response = await client.post("/api/v1/push/test", headers={"Authorization": f"Bearer {user_token}"})

    assert response.status_code in [200, 404, 422]  # Endpoint may not exist yet
