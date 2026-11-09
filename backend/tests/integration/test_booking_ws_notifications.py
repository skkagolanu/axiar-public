"""Booking-status WebSocket push: a status transition must
reach a connected client without depending on Kafka (event_bus.producer is
None in this test environment -- exactly why the WS push is wired directly
into BookingRepository.update_status rather than routed through a consumer).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.tenant_context import set_current_tenant
from app.core.websocket import manager as ws_manager
from app.domain.booking.models import BookingStatus
from app.domain.booking.repository import BookingRepository


@pytest.mark.integration
async def test_status_update_delivers_to_connected_ws_client(
    db_session, default_tenant_id, test_customer, test_provider, test_service, monkeypatch
):
    # Force the guaranteed-synchronous local-delivery path: send_personal_message
    # prefers publishing to Redis pub/sub when available, which this process
    # never subscribes back to in tests (ws_manager.start() only runs in
    # main.py's lifespan) -- forcing local delivery keeps this deterministic
    # regardless of what other test modules have already connected cache_manager.
    monkeypatch.setattr("app.core.cache.cache_manager.redis", None)

    fake_ws = MagicMock()
    fake_ws.accept = AsyncMock()
    fake_ws.send_json = AsyncMock()
    await ws_manager.connect(test_customer, fake_ws)
    try:
        set_current_tenant(default_tenant_id)
        try:
            repo = BookingRepository(db_session)
            booking = await repo.create(
                customer_id=test_customer,
                provider_id=test_provider,
                service_id=test_service,
                scheduled_time=datetime.now(timezone.utc) + timedelta(days=2),
                duration_minutes=60,
                location_postcode="NG7 2RD",
                base_price_cents=5000,
            )
            await db_session.commit()

            await repo.update_status(booking.id, BookingStatus.CONFIRMED)
            await db_session.commit()
        finally:
            set_current_tenant(None)

        fake_ws.send_json.assert_called_once_with(
            {
                "type": "booking_status_update",
                "booking_id": str(booking.id),
                "old_status": "pending",
                "new_status": "confirmed",
            }
        )
    finally:
        ws_manager.disconnect(test_customer, fake_ws)
