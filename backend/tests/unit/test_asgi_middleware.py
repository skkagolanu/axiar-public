"""ASGI optimization must preserve tracing, tenant isolation, and security headers."""

import asyncio
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.responses import JSONResponse

from app.core.correlation import CorrelationIDMiddleware, get_correlation_id
from app.core.metrics import RequestMetricsMiddleware
from app.core.security_middleware import RequestLoggingMiddleware, SecurityHeadersMiddleware
from app.core.tenant_context import get_current_tenant
from app.core.tenant_middleware import TenantMiddleware


@pytest.mark.unit
async def test_parallel_requests_restore_context_and_headers(monkeypatch):
    before_tenant, before_trace = get_current_tenant(), get_correlation_id()

    async def endpoint(scope, receive, send):
        await asyncio.sleep(0)
        await JSONResponse({"tenant": str(get_current_tenant()), "trace": get_correlation_id()})(scope, receive, send)

    async def resolve(self, identifier):
        await asyncio.sleep(0)
        return {"id": identifier, "is_active": True}

    monkeypatch.setattr(TenantMiddleware, "_resolve", resolve)
    app = RequestMetricsMiddleware(
        CorrelationIDMiddleware(TenantMiddleware(RequestLoggingMiddleware(SecurityHeadersMiddleware(endpoint))))
    )
    tenants = [str(uuid4()), str(uuid4())]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        responses = await asyncio.gather(
            *(
                client.get("/probe", headers={"X-Tenant-ID": tenant, "X-Request-ID": f"trace-{i}"})
                for i, tenant in enumerate(tenants)
            )
        )
    for i, response in enumerate(responses):
        assert response.json() == {"tenant": tenants[i], "trace": f"trace-{i}"}
        assert response.headers["X-Request-ID"] == f"trace-{i}"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["Content-Security-Policy"] == "default-src 'self'"
        assert float(response.headers["X-Process-Time"]) >= 0
    assert get_current_tenant() == before_tenant
    assert get_correlation_id() == before_trace


@pytest.mark.unit
@pytest.mark.parametrize("resolved, expected", [({}, 404), ({"id": str(uuid4()), "is_active": False}, 403)])
async def test_invalid_tenant_stays_fail_closed(monkeypatch, resolved, expected):
    called = False

    async def endpoint(scope, receive, send):
        nonlocal called
        called = True

    async def resolve(self, identifier):
        return resolved

    monkeypatch.setattr(TenantMiddleware, "_resolve", resolve)
    async with AsyncClient(transport=ASGITransport(app=TenantMiddleware(endpoint)), base_url="http://test") as client:
        response = await client.get("/protected", headers={"X-Tenant-ID": str(uuid4())})
    assert response.status_code == expected
    assert not called


@pytest.mark.unit
def test_metrics_aggregate_all_worker_counters(tmp_path, monkeypatch):
    import os
    import subprocess
    import sys

    from app.core.config import settings
    from app.core.metrics import get_metrics

    env = dict(os.environ, PROMETHEUS_MULTIPROC_DIR=str(tmp_path))
    for count in [3, 5]:
        subprocess.run(
            [
                sys.executable,
                "-c",
                f"from prometheus_client import Counter; Counter('worker_probe_total', 'probe').inc({count})",
            ],
            env=env,
            check=True,
        )
    monkeypatch.setattr(settings, "PROMETHEUS_MULTIPROC_DIR", str(tmp_path))
    assert "worker_probe_total 8.0" in bytes(get_metrics().body).decode()
