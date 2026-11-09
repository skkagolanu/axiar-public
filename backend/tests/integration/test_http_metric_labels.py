"""Per-object URLs must share one Prometheus route label."""

from uuid import uuid4

import pytest


@pytest.mark.integration
async def test_booking_metric_labels_are_bounded(async_client, user_token):
    paths = [f"/api/v1/bookings/{uuid4()}" for _ in range(3)]
    for path in paths:
        response = await async_client.get(path, headers={"Authorization": f"Bearer {user_token}"})
        assert response.status_code == 404
    metrics = await async_client.get("/api/v1/metrics")
    assert 'endpoint="/api/v1/bookings/{booking_id}"' in metrics.text
    assert all(f'endpoint="{path}"' not in metrics.text for path in paths)
