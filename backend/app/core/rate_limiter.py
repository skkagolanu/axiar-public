from typing import Any, Awaitable, Callable, Optional

import redis.asyncio as redis
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from app.core.client_ip import get_client_ip
from app.core.config import settings
from app.core.request_paths import HEALTH_CHECK_PATHS

_FIXED_WINDOW_SCRIPT = """
local current = redis.call('incr', KEYS[1])
local ttl = redis.call('ttl', KEYS[1])
if current == 1 or ttl < 0 then
    redis.call('expire', KEYS[1], ARGV[1])
    ttl = tonumber(ARGV[1])
end
return {current, ttl}
"""


class RateLimiter:
    def __init__(self) -> None:
        self.redis_client: Optional[Any] = None

    async def init(self) -> None:
        """Initialize Redis connection"""
        if settings.DEMO_MODE or not settings.REDIS_URL:
            self.redis_client = None
            return
        self.redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
        )

    async def close(self) -> None:
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()

    def _get_key(self, identifier: str, window: str) -> str:
        """Generate rate limit key"""
        return f"rate_limit:{window}:{identifier}"

    async def check_rate_limit(
        self,
        identifier: str,
        max_requests: int,
        window_seconds: int,
        window_name: str = "default",
        fail_closed: bool = False,
    ) -> tuple[bool, int, int]:
        'Rate limiter.'
        # Sensitive paths use the configured Redis-outage policy. Demo mode
        # allows requests through when Redis is unavailable.
        if settings.DEMO_MODE:
            fail_closed = False

        if not self.redis_client:
            return (False, 0, 30) if fail_closed else (True, max_requests, 0)

        try:
            # The increment and TTL assignment must be one Redis operation. A
            # GET/decision/INCR sequence lets concurrent requests overspend the
            # limit, while a failed INCR-before-EXPIRE can leak a permanent key.
            count, ttl = await self.redis_client.eval(
                _FIXED_WINDOW_SCRIPT,
                1,
                self._get_key(identifier, window_name),
                window_seconds,
            )
            count = int(count)
            ttl = max(int(ttl), 0)
            return count <= max_requests, max(max_requests - count, 0), ttl

        except Exception:
            if fail_closed:
                # Reject with a short retry-after rather than leaking "Redis is
                # down" as a distinguishable signal to an unauthenticated caller
                # probing login/register — same 429 shape as a real rate limit.
                return False, 0, 30
            return True, max_requests, 0


rate_limiter = RateLimiter()

# Everything else fails open (see check_rate_limit's default). These are exactly
# the endpoints brute-force/credential-stuffing/email-bombing target, so briefly
# rejecting legitimate traffic during a rare Redis outage is the right trade —
# the alternative (silently disabling their rate limits) is worse.
AUTH_SENSITIVE_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/magic-link",
    "/api/v1/auth/verify-magic-link",
    # Unauthenticated, and it emails a 24h magic link to any address the caller names —
    # the same email-bombing surface as /auth/magic-link, reachable without an account.
    "/api/v1/bookings/guest",
}


async def rate_limit_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Rate limiting middleware"""
    path = request.url.path
    if path in HEALTH_CHECK_PATHS:
        return await call_next(request)

    # Get user identifier (IP or user ID)
    identifier = get_client_ip(request)

    if hasattr(request.state, "user") and request.state.user:
        identifier = f"user:{request.state.user.id}"

    # Different limits for different endpoints
    limits = {
        "/api/v1/auth/login": (5, 300),  # 5 per 5 minutes
        "/api/v1/auth/register": (3, 3600),  # 3 per hour
        "/api/v1/auth/magic-link": (
            3,
            3600,
        ),  # 3 per hour — sends an email, abuse-prone
        "/api/v1/auth/verify-magic-link": (
            10,
            300,
        ),  # 10 per 5 minutes — token brute-force guard
        "/api/v1/auth/refresh": (
            20,
            300,
        ),  # 20 per 5 minutes — legitimate clients refresh often
        "/api/v1/bookings/guest": (
            5,
            3600,
        ),  # 5 per hour — unauthenticated, sends a magic-link email
        "default": (100, 60),  # 100 per minute
    }

    max_requests, window = limits.get(path, limits["default"])

    allowed, remaining, reset = await rate_limiter.check_rate_limit(
        identifier, max_requests, window, path, fail_closed=path in AUTH_SENSITIVE_PATHS
    )

    if not allowed:
        # Middleware rejections return a response without entering router exception handling.
        return JSONResponse(
            status_code=429,
            content={"detail": f"Rate limit exceeded. Try again in {reset} seconds"},
            headers={"Retry-After": str(reset)},
        )

    response: Response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(max_requests)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(reset)

    return response
