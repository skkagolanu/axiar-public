from unittest.mock import patch

import pytest

from app.core.ai_assistant import AIAssistant
from app.core.cache import CacheManager
from app.core.config import settings
from app.core.demo_integrations import demo_integrations


@pytest.mark.asyncio
async def test_demo_cache_never_constructs_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    monkeypatch.setattr(settings, "REDIS_URL", "redis://should-not-be-used:6379")

    with patch("app.core.cache.redis.from_url") as from_url:
        cache = CacheManager()
        await cache.init()

    from_url.assert_not_called()
    assert await cache.get("missing") is None
    assert await cache.set("key", "value") is False


@pytest.mark.asyncio
async def test_demo_ai_is_deterministic_and_never_calls_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DEMO_MODE", True)

    with patch("app.core.ai_assistant.httpx.AsyncClient") as client:
        response = await AIAssistant().generate_response("How is today looking?")

    client.assert_not_called()
    assert response == demo_integrations.ai_response("How is today looking?")


def test_demo_geocoder_is_keyless_and_region_bounded() -> None:
    assert demo_integrations.geocode_postcode("SW1A 1AA") == (51.5010, -0.1416)
    assert demo_integrations.geocode_postcode("90210") is None
