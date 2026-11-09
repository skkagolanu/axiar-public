"""Correlation ID middleware for request tracing.

Assigns every request a correlation id (honoring an inbound ``X-Request-ID`` /
``X-Correlation-ID`` if present), stashes it in a ContextVar so any log record
emitted during the request can pick it up, and echoes it back on the response.
"""

import uuid
from contextvars import ContextVar

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Default "" (not None) so the JSON log formatter can treat absence as "no id"
# without branching on type.
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


class CorrelationIDMiddleware:
    """Attach a correlation id to every request for distributed tracing."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        correlation_id = request.headers.get("X-Request-ID") or request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        token = correlation_id_var.set(correlation_id)

        async def traced_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["X-Request-ID"] = correlation_id
            await send(message)

        try:
            await self.app(scope, receive, traced_send)
        finally:
            correlation_id_var.reset(token)


def get_correlation_id() -> str:
    """Return the current request's correlation id (``""`` outside a request)."""
    return correlation_id_var.get()
