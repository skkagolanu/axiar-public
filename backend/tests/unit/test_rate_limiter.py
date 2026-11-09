"""Rate limiter: 429 path + the fail-open/fail-closed Redis-outage decision."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.responses import Response

from app.core.rate_limiter import RateLimiter
from app.core.request_paths import HEALTH_CHECK_PATHS


@pytest.mark.asyncio
async def test_allows_request_under_limit():
    limiter = RateLimiter()
    limiter.redis_client = AsyncMock()
    limiter.redis_client.eval.return_value = [3, 58]

    allowed, remaining, reset = await limiter.check_rate_limit("id", max_requests=5, window_seconds=60)

    assert allowed is True
    assert remaining == 2
    assert reset == 58


@pytest.mark.asyncio
async def test_returns_429_shape_when_over_limit():
    limiter = RateLimiter()
    limiter.redis_client = AsyncMock()
    limiter.redis_client.eval.return_value = [6, 42]

    allowed, remaining, reset = await limiter.check_rate_limit("id", max_requests=5, window_seconds=60)

    assert allowed is False
    assert remaining == 0
    assert reset == 42


@pytest.mark.asyncio
async def test_redis_outage_fails_open_by_default():
    limiter = RateLimiter()
    limiter.redis_client = AsyncMock()
    limiter.redis_client.eval.side_effect = ConnectionError("redis down")

    allowed, remaining, _ = await limiter.check_rate_limit("id", max_requests=5, window_seconds=60)

    assert allowed is True
    assert remaining == 5


@pytest.mark.asyncio
async def test_redis_outage_fails_closed_for_sensitive_paths():
    limiter = RateLimiter()
    limiter.redis_client = AsyncMock()
    limiter.redis_client.eval.side_effect = ConnectionError("redis down")

    allowed, remaining, reset = await limiter.check_rate_limit("id", max_requests=5, window_seconds=60, fail_closed=True)

    assert allowed is False
    assert remaining == 0
    assert reset == 30


@pytest.mark.asyncio
async def test_no_redis_client_fails_open_by_default():
    limiter = RateLimiter()  # redis_client is None (init() never called)

    allowed, remaining, _ = await limiter.check_rate_limit("id", max_requests=5, window_seconds=60)

    assert allowed is True
    assert remaining == 5


@pytest.mark.asyncio
async def test_no_redis_client_fails_closed_for_sensitive_paths():
    limiter = RateLimiter()

    allowed, remaining, reset = await limiter.check_rate_limit("id", max_requests=5, window_seconds=60, fail_closed=True)

    assert allowed is False
    assert reset == 30


@pytest.mark.asyncio
async def test_middleware_rejection_is_a_response_not_an_exception(monkeypatch):
    """Return an HTTP 429 response directly for rejected middleware requests."""
    from app.core import rate_limiter as rl

    monkeypatch.setattr(rl.rate_limiter, "redis_client", None)  # simulate Redis down

    request = MagicMock()
    request.client.host = "203.0.113.9"
    request.state = MagicMock(spec=[])  # no .user attribute
    request.url.path = "/api/v1/auth/login"  # AUTH_SENSITIVE_PATHS -> fail closed

    async def call_next(_):  # must never be reached
        raise AssertionError("request should have been rejected before the app")

    response = await rl.rate_limit_middleware(request, call_next)

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "30"


@pytest.mark.asyncio
async def test_demo_mode_fails_open_on_sensitive_paths(monkeypatch):
    """Demo mode allows authentication requests through during a Redis outage."""
    from app.core import rate_limiter as rl

    monkeypatch.setattr(rl.settings, "DEMO_MODE", True)
    limiter = RateLimiter()  # redis_client is None (Redis down)

    allowed, _, _ = await limiter.check_rate_limit("id", max_requests=5, window_seconds=60, fail_closed=True)

    assert allowed is True


@pytest.mark.asyncio
@pytest.mark.parametrize("path", sorted(HEALTH_CHECK_PATHS))
async def test_health_check_bypasses_rate_limiter(monkeypatch, path):
    from app.core import rate_limiter as rl

    check = AsyncMock(side_effect=AssertionError("health checks must not touch Redis"))
    monkeypatch.setattr(rl.rate_limiter, "check_rate_limit", check)
    request = MagicMock()
    request.url.path = path
    expected = Response(status_code=200)
    call_next = AsyncMock(return_value=expected)

    response = await rl.rate_limit_middleware(request, call_next)

    assert response is expected
    check.assert_not_awaited()


def test_all_health_checks_bypass_tenant_resolution():
    from app.core.request_paths import HEALTH_CHECK_PATHS
    from app.core.tenant_middleware import _EXEMPT_PATHS

    assert HEALTH_CHECK_PATHS <= _EXEMPT_PATHS


def test_render_proxy_header_separates_client_buckets(monkeypatch):
    from app.core import client_ip

    monkeypatch.setattr(client_ip.settings, "RATE_LIMIT_TRUSTED_PROXY_HEADER", "CF-Connecting-IP")
    request = MagicMock()
    request.headers = {"CF-Connecting-IP": "203.0.113.17"}
    request.client.host = "10.0.0.4"

    assert client_ip.get_client_ip(request) == "203.0.113.17"


def test_invalid_proxy_header_falls_back_to_socket_ip(monkeypatch):
    from app.core import client_ip

    monkeypatch.setattr(client_ip.settings, "RATE_LIMIT_TRUSTED_PROXY_HEADER", "CF-Connecting-IP")
    request = MagicMock()
    request.headers = {"CF-Connecting-IP": "spoofed"}
    request.client.host = "10.0.0.4"

    assert client_ip.get_client_ip(request) == "10.0.0.4"
