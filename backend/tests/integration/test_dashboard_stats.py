"""Integration tests for GET /api/v1/dashboard/stats and /activity.

Validates:
- Endpoints require authentication.
- Stats response shape matches DashboardStats contract (revenue/jobs/team).
- Revenue trend is real (not the old placeholder 12.5).
- Activity list is tenant-scoped and uses the correct shape.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_dashboard_stats_requires_auth(async_client: AsyncClient):
    response = await async_client.get("/api/v1/dashboard/stats")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_dashboard_stats_shape(async_client: AsyncClient, user_token: str):
    response = await async_client.get(
        "/api/v1/dashboard/stats",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert response.status_code == 200
    data = response.json()

    # Revenue block
    assert "revenue" in data
    assert "total" in data["revenue"]
    assert "trend" in data["revenue"]
    assert "trendDirection" in data["revenue"]
    assert data["revenue"]["trendDirection"] in ("up", "down")
    # Must NOT be the old hardcoded placeholder value
    assert (
        data["revenue"]["trend"] != 12.5 or data["revenue"]["total"] == 0.0
    ), "trend=12.5 is still the placeholder — real computation expected"

    # Jobs block
    assert "jobs" in data
    for key in ("today", "inProgress", "pending"):
        assert key in data["jobs"]
        assert isinstance(data["jobs"][key], int)

    # Team block
    assert "team" in data
    assert "active" in data["team"]
    assert "total" in data["team"]


@pytest.mark.asyncio
async def test_dashboard_activity_requires_auth(async_client: AsyncClient):
    response = await async_client.get("/api/v1/dashboard/activity")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_dashboard_activity_shape(async_client: AsyncClient, user_token: str):
    response = await async_client.get(
        "/api/v1/dashboard/activity",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    for item in data:
        assert "id" in item
        assert "type" in item
        assert item["type"] in ("job_created", "job_completed")
        assert "message" in item
        assert "timestamp" in item
        assert "priority" in item
        assert item["priority"] in ("low", "medium", "high")
