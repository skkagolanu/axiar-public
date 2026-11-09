import uuid
from typing import Any, Dict

from fastapi import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.cache import cache_manager
from app.core.database import db_manager
from app.core.request_paths import HEALTH_CHECK_PATHS
from app.core.tenant_context import tenant_context
from app.domain.tenant.repository import TenantRepository

# Paths that must work before/without tenant resolution.
_EXEMPT_PATHS = {
    "/",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/health",
    *HEALTH_CHECK_PATHS,
}

# How long a resolved tenant lookup is cached (seconds). Trade-off: a deactivated tenant
# stays usable for up to this window. Keep modest.
_TENANT_CACHE_TTL = 300


class TenantMiddleware:
    """Extract tenant from request and set in context (Redis-cached to avoid a DB hit per request)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in _EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        identifier = request.headers.get("X-Tenant-ID") or request.headers.get("X-Tenant-Slug")
        data = await self._resolve(identifier or "default")
        if identifier and not data:
            await JSONResponse({"detail": "Tenant not found"}, status_code=404)(scope, receive, send)
            return
        if data and not data.get("is_active"):
            await JSONResponse({"detail": "Tenant is inactive"}, status_code=403)(scope, receive, send)
            return
        tenant_id = uuid.UUID(data["id"]) if data else None
        token = tenant_context.set(tenant_id)
        request.state.tenant_id = tenant_id
        try:
            await self.app(scope, receive, send)
        finally:
            tenant_context.reset(token)

    async def _resolve(self, identifier: str) -> Dict[str, Any] | None:
        """Resolve a tenant identifier (UUID or slug) to {"id", "is_active"}.

        Returns {} for a known-missing tenant, or None only if resolution couldn't run.
        Cached in Redis; falls back to the DB on cache miss/unavailability.
        """
        cache_key = f"tenant:resolve:{identifier}"
        cached = await cache_manager.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[no-any-return]

        async with db_manager.get_session() as session:
            repo = TenantRepository(session)
            try:
                tenant = await repo.get_by_id(uuid.UUID(identifier))
            except ValueError:
                tenant = await repo.get_by_slug(identifier)

        data = {"id": str(tenant.id), "is_active": tenant.is_active} if tenant else {}
        await cache_manager.set(cache_key, data, ttl=_TENANT_CACHE_TTL)
        return data
