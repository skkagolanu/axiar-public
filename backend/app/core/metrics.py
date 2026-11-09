import time
from functools import wraps
from typing import Any, Callable

from fastapi import Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram, generate_latest, multiprocess
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings

# Metrics
http_requests_total = Counter("http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"])

http_request_duration_seconds = Histogram("http_request_duration_seconds", "HTTP request duration", ["method", "endpoint"])

active_connections = Gauge("active_connections", "Active WebSocket connections")

booking_operations = Counter("booking_operations_total", "Booking operations", ["operation", "status"])

payment_operations = Counter("payment_operations_total", "Payment operations", ["operation", "status"])

database_query_duration = Histogram("database_query_duration_seconds", "Database query duration", ["query_type"])

cache_operations = Counter("cache_operations_total", "Cache operations", ["operation", "status"])


class RequestMetricsMiddleware:
    """Observe the response start without another task group/stream per request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()

        async def measured_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                duration = time.perf_counter() - started
                MutableHeaders(scope=message)["X-Process-Time"] = str(duration)
                route = scope.get("fastapi", {}).get("effective_route_context") or scope.get("route")
                path = getattr(route, "path", "unmatched")
                http_requests_total.labels(method=scope["method"], endpoint=path, status=str(message["status"])).inc()
                http_request_duration_seconds.labels(method=scope["method"], endpoint=path).observe(duration)
            await send(message)

        await self.app(scope, receive, measured_send)


def track_request_metrics(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to track request metrics"""

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        start_time = time.time()
        status = "success"

        try:
            result = await func(*args, **kwargs)
            return result
        except Exception as e:
            status = "error"
            raise e
        finally:
            duration = time.time() - start_time
            http_request_duration_seconds.labels(method="unknown", endpoint="unknown").observe(duration)

    return wrapper


def get_metrics() -> Response:
    """Endpoint to expose Prometheus metrics"""
    if settings.PROMETHEUS_MULTIPROC_DIR:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry, path=settings.PROMETHEUS_MULTIPROC_DIR)
        return Response(content=generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
