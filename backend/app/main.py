import asyncio
import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.sessions import SessionMiddleware

from app.api.v1.router import v1_router
from app.core.cache import cache_manager
from app.core.config import settings
from app.core.correlation import CorrelationIDMiddleware
from app.core.database import db_manager
from app.core.event_bus import event_bus
from app.core.exceptions import (
    AppException,
    app_exception_handler,
    database_exception_handler,
    generic_exception_handler,
    validation_exception_handler,
)
from app.core.metrics import RequestMetricsMiddleware
from app.core.observability import flush_sentry, init_sentry
from app.core.rate_limiter import rate_limit_middleware, rate_limiter
from app.core.security_middleware import RequestLoggingMiddleware, SecurityHeadersMiddleware
from app.core.tenant_middleware import TenantMiddleware
from app.core.vector_store import vector_store

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("Application starting up")
    sentry_initialized = init_sentry()
    await cache_manager.init()
    await rate_limiter.init()
    await event_bus.start()
    vector_store.init()

    # Register domain event consumers (best-effort — degrade gracefully when Kafka is down)
    from app.consumers import dispatch_booking_event, dispatch_payment_event

    await event_bus.subscribe("axiar.booking.events", "axiar-booking-notifications", dispatch_booking_event)
    await event_bus.subscribe("axiar.payment.events", "axiar-payment-notifications", dispatch_payment_event)
    from app.core.websocket import manager as ws_manager

    await ws_manager.start()

    # Start background outbox relay
    from app.consumers.outbox_relay import relay_outbox

    outbox_task = asyncio.create_task(relay_outbox())

    # Create the default tenant safely when multiple workers start concurrently.
    # A unique-slug conflict means another worker already created it.
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError

    from app.domain.tenant.models import Tenant

    async with db_manager.get_session() as session:
        result = await session.execute(select(Tenant).where(Tenant.slug == "default"))
        if not result.scalar_one_or_none():
            try:
                default_tenant = Tenant(name="Default Organization", slug="default", is_active=True, settings={})
                session.add(default_tenant)
                await session.commit()
                logger.info(f"Created default tenant: {default_tenant.id}")
            except IntegrityError:
                await session.rollback()
                logger.info("Default tenant already created by a concurrent worker")

    yield
    # Shutdown
    logger.info("Application shutting down")
    from app.core.websocket import manager as ws_manager

    flush_sentry(sentry_initialized)

    await ws_manager.stop()

    if outbox_task and not outbox_task.done():
        outbox_task.cancel()
        try:
            await outbox_task
        except asyncio.CancelledError:
            pass

    await event_bus.stop()
    await rate_limiter.close()
    await cache_manager.close()
    for engine in db_manager.engines.values():
        await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="AI-Powered Operating System for Service Teams",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# CORS middleware — explicit allowlist always (never wildcard origins with credentials,
# which is invalid per the CORS spec and a security smell).
cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
# CORS uses an explicit allowlist. FRONTEND_URL may contain comma-separated
# SPA origins, which are merged with the configured CORS origins.
for frontend_origin in (settings.FRONTEND_URL or "").split(","):
    frontend_origin = frontend_origin.strip()
    if frontend_origin and frontend_origin not in cors_origins:
        cors_origins.append(frontend_origin)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Process-Time"],
    max_age=3600,
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET_KEY,
)

# Security middleware
allowed_hosts = [h.strip() for h in settings.ALLOWED_HOSTS.split(",")] if settings.ALLOWED_HOSTS != "*" else ["*"]
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
app.add_middleware(SecurityHeadersMiddleware, debug=settings.DEBUG)
app.add_middleware(RequestLoggingMiddleware)
# Correlation id: added after RequestLogging so it wraps it (outer) and the id is

app.add_middleware(CorrelationIDMiddleware)

# Compression middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Tenant isolation middleware
app.add_middleware(TenantMiddleware)

# Rate limiting middleware (configurable; set RATE_LIMIT_ENABLED=false to disable, e.g. in tests)
if settings.RATE_LIMIT_ENABLED:
    app.middleware("http")(rate_limit_middleware)


app.add_middleware(RequestMetricsMiddleware)


# Register exception handlers (OWASP compliant - no stack traces exposed)
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(SQLAlchemyError, database_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)


# Include routers
app.include_router(v1_router)


@app.get("/")
async def root():
    """Root endpoint — does not enumerate routes (avoid leaking the API surface)."""
    return {
        "message": "Axiar API",
        "version": settings.VERSION,
        "docs": "/docs" if settings.DEBUG else None,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
