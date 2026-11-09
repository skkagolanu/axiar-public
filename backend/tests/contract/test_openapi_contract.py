"""Schema-generated GET contract checks using the shared asynchronous API client.
Hypothesis generates OpenAPI-conformant requests; the fixture-owned ASGI transport
keeps database access on the test session event loop."""

from contextlib import asynccontextmanager

import httpx
import pytest
import respx
import schemathesis
from hypothesis import HealthCheck, assume, settings

from app.core.config import settings as app_settings
from app.main import app


@asynccontextmanager
async def _noop_lifespan(_app):
    yield


# from_asgi() below does one schema-loading GET through schemathesis's own
# starlette_testclient.TestClient, whose portal-thread event loop shouldn't touch this
# app's real lifespan (Kafka event bus, outbox relay) any more than the rest of the
# suite's async_client fixture already avoids doing (see the module docstring).
app.router.lifespan_context = _noop_lifespan

# Additional exclusions can be declared for a scoped contract run.
_KNOWN_FAILING_PATHS: list[str] = []

# Tag strings must match each router's OWN `APIRouter(tags=[...])` when no tags= is
# passed to include_router() (ai/ai_scheduling/push), vs. the tags= kwarg passed AT
# include_router() for the others (payments/oauth/voice) -- these come from two
# different places in router.py and don't share a naming convention, so verify
# against the actual endpoint file before assuming a lowercase guess matches.
_EXCLUDED_TAGS = [
    "payments",
    "oauth",
    "voice",
    "AI Assistant",
    "AI Scheduling",
    "Push Notifications",
]

schema = (
    schemathesis.openapi.from_asgi("/openapi.json", app)
    .include(method="GET")
    .exclude(tag=_EXCLUDED_TAGS)
    .exclude(path=_KNOWN_FAILING_PATHS)
)


def _is_ascii(value: str) -> bool:
    try:
        value.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


@schema.parametrize()
@pytest.mark.contract
# admin_token/async_client are each created once per test (not per generated example)
# and never mutated -- reusing them across examples is safe, so suppress Hypothesis's
# generic function-scoped-fixture warning rather than restructure around it.
# max_examples=5: each example is a real request through the full app/DB stack (not
# in-memory), so Hypothesis's ~100-example default blew the backend-test job's 20min
# CI timeout across ~30 GET operations. 5 still exercises multiple randomized inputs
# per endpoint without paying for exhaustive fuzzing on every CI run.
@settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
async def test_api_contract(case, admin_token, async_client, monkeypatch):
    kwargs = case.as_transport_kwargs(headers={"Authorization": f"Bearer {admin_token}"})
    kwargs.pop("cookies", None)  # httpx deprecates per-request cookies=<empty dict>
    # httpx enforces ASCII-only header values (a real HTTP requirement most clients also
    # enforce); Hypothesis occasionally generates a schema-valid string that isn't
    # ASCII-transmittable as a header. That's not a claim about this app's behavior, so
    # discard the example (assume) rather than fail on an unconstructable request.
    assume(all(_is_ascii(v) for v in kwargs.get("headers", {}).values()))
    if case.operation.path == "/api/v1/providers/search/by-postcode":
        # Exercise the configured endpoint and its real PostGIS query without
        # external credentials or a network dependency. Missing configuration
        # has a separate explicit 501 regression; this is not a load-test mock.
        monkeypatch.setattr(app_settings, "GOOGLE_MAPS_API_KEY", "contract-test-only")
        with respx.mock(assert_all_called=False) as external:
            external.get("https://maps.googleapis.com/maps/api/geocode/json").respond(
                200,
                json={
                    "status": "OK",
                    "results": [{"geometry": {"location": {"lat": 52.95, "lng": -1.15}}}],
                },
            )
            response = await async_client.request(**kwargs)
    else:
        response = await async_client.request(**kwargs)
    assert (
        response.status_code < 500
    ), f"{kwargs['method']} {kwargs['url']} crashed with {response.status_code}: {response.text[:500]}"
