"""Canonical infrastructure paths shared by request middleware."""

HEALTH_CHECK_PATHS = frozenset(
    {
        "/api/v1/health",
        "/api/v1/ready",
        "/api/v1/monitoring/health/live",
        "/api/v1/monitoring/health/ready",
    }
)
