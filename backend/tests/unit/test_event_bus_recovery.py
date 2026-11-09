"""A Kafka outage at startup must retain the intended consumer registrations."""

from unittest.mock import AsyncMock

import pytest

from app.core.event_bus import EventBus


@pytest.mark.unit
async def test_reconnect_restores_subscriptions(monkeypatch):
    bus = EventBus()
    handler = AsyncMock()
    await bus.subscribe("axiar.booking.events", "test-group", handler)
    assert bus._subscriptions["test-group:axiar.booking.events"] == ("axiar.booking.events", "test-group", handler)

    async def reconnect():
        bus.producer = AsyncMock()

    start = AsyncMock(side_effect=reconnect)
    subscribe = AsyncMock()
    monkeypatch.setattr(bus, "start", start)
    monkeypatch.setattr(bus, "subscribe", subscribe)
    await bus.ensure_connected()
    start.assert_awaited_once()
    subscribe.assert_awaited_once_with("axiar.booking.events", "test-group", handler)
