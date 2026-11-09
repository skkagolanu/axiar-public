"""Integration tests for the correlation-id middleware (X-Request-ID tracing)."""

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_correlation_id_generated_when_absent(async_client: AsyncClient):
    """A request with no correlation header gets a generated, valid UUID echoed back."""
    response = await async_client.get("/")
    request_id = response.headers.get("X-Request-ID")
    assert request_id, "X-Request-ID should be set on every response"
    # Generated ids are UUID4 — this raises (failing the test) if it isn't a UUID.
    uuid.UUID(request_id)


@pytest.mark.asyncio
async def test_correlation_id_honors_inbound_header(async_client: AsyncClient):
    """An inbound X-Request-ID is preserved and echoed back unchanged."""
    incoming = "test-correlation-123"
    response = await async_client.get("/", headers={"X-Request-ID": incoming})
    assert response.headers.get("X-Request-ID") == incoming


@pytest.mark.asyncio
async def test_correlation_id_honors_x_correlation_id_alias(async_client: AsyncClient):
    """The X-Correlation-ID alias is also accepted as the inbound source."""
    incoming = "alias-456"
    response = await async_client.get("/", headers={"X-Correlation-ID": incoming})
    assert response.headers.get("X-Request-ID") == incoming
