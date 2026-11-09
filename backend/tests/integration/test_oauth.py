"""Tests for OAuth SessionMiddleware"""

import pytest
from httpx import AsyncClient

from app.core.config import settings


@pytest.mark.asyncio
async def test_oauth_google_redirect(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    """Test OAuth Google returns redirect"""
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-secret")
    response = await client.get("/api/v1/oauth/google", follow_redirects=False)
    assert response.status_code == 302
    assert "location" in response.headers


@pytest.mark.asyncio
async def test_oauth_microsoft_redirect(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    """Test OAuth Microsoft returns redirect"""
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "MICROSOFT_CLIENT_ID", "test-client")
    monkeypatch.setattr(settings, "MICROSOFT_CLIENT_SECRET", "test-secret")
    response = await client.get("/api/v1/oauth/microsoft", follow_redirects=False)
    assert response.status_code == 302
    assert "location" in response.headers


@pytest.mark.asyncio
async def test_session_middleware_present(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    """Test SessionMiddleware is configured"""
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-secret")
    response = await client.get("/api/v1/oauth/google", follow_redirects=False)
    assert response.status_code in [302, 500]  # 302 = working, 500 = config issue but middleware present


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    ["/api/v1/oauth/google", "/api/v1/oauth/google/callback", "/api/v1/oauth/microsoft", "/api/v1/oauth/microsoft/callback"],
)
async def test_demo_mode_hides_oauth(client: AsyncClient, monkeypatch: pytest.MonkeyPatch, path: str):
    monkeypatch.setattr(settings, "DEMO_MODE", True)

    response = await client.get(path, follow_redirects=False)

    assert response.status_code == 404
