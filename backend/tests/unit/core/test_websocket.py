import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.cache import cache_manager
from app.core.websocket import ConnectionManager


@pytest.mark.asyncio
async def test_pubsub_timeout_does_not_block_application_startup(monkeypatch):
    async def stalled_subscribe(_channel):
        await asyncio.Event().wait()

    pubsub = MagicMock()
    pubsub.subscribe = AsyncMock(side_effect=stalled_subscribe)
    pubsub.aclose = AsyncMock()
    redis_backend = MagicMock()
    redis_backend.pubsub.return_value = pubsub
    monkeypatch.setattr(cache_manager, "redis", redis_backend)

    manager = ConnectionManager()
    manager.STARTUP_TIMEOUT_SECONDS = 0.01
    await asyncio.wait_for(manager.start(), timeout=0.2)

    assert manager._pubsub is None
    assert manager._listener_task is None
    pubsub.aclose.assert_awaited_once()
