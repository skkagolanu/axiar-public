import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


def init_sentry() -> bool:
    """Initialize the Sentry SDK if SENTRY_DSN is configured.

    Returns True if Sentry was initialized, False otherwise (DSN unset or the
    ``sentry-sdk`` package is unavailable) — callers use this to decide whether
    to flush on shutdown.
    """
    if not settings.SENTRY_DSN:
        return False
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN.get_secret_value(),
            environment=settings.ENVIRONMENT,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        )
        logger.info("Sentry SDK initialized")
        return True
    except ImportError:
        logger.warning("Sentry SDK not installed, skipping initialization")
        return False


def flush_sentry(initialized: bool) -> None:
    """Flush buffered Sentry events on shutdown. No-op if never initialized."""
    if not initialized:
        return
    try:
        import sentry_sdk

        sentry_sdk.flush()
    except Exception:
        pass
