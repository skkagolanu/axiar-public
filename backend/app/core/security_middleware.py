import logging
import time

from fastapi import Request
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.client_ip import get_client_ip

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware:
    """Add security headers to all responses"""

    def __init__(self, app: ASGIApp, debug: bool = False) -> None:
        self.app = app
        self.debug = debug

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def secured_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                self._set_headers(MutableHeaders(scope=message))
            await send(message)

        await self.app(scope, receive, secured_send)

    def _set_headers(self, headers: MutableHeaders) -> None:

        # Security headers
        headers["X-Content-Type-Options"] = "nosniff"
        headers["X-Frame-Options"] = "DENY"
        headers["X-XSS-Protection"] = "1; mode=block"
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # Relaxed CSP for development to allow Swagger UI CDN resources
        if self.debug:
            headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: https://fastapi.tiangolo.com"
            )
        else:
            headers["Content-Security-Policy"] = "default-src 'self'"

        headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"


class RequestLoggingMiddleware:
    """Log all requests for security monitoring"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        started = time.perf_counter()
        logger.info(
            f"Request: {request.method} {request.url.path}",
            extra={
                "method": request.method,
                "path": request.url.path,
                "client_ip": get_client_ip(request),
                "cf_ray": request.headers.get("cf-ray"),
                "user_agent": request.headers.get("user-agent"),
            },
        )

        async def logged_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                duration = time.perf_counter() - started
                logger.info(
                    f"Response: {message['status']} ({duration:.3f}s)",
                    extra={"status_code": message["status"], "process_time": duration},
                )
            await send(message)

        await self.app(scope, receive, logged_send)
