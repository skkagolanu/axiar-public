import httpx
import pytest

from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint():
    """Test health check endpoint"""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


@pytest.mark.asyncio
async def test_root_endpoint():
    """Test root endpoint"""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Axiar API"
        assert "version" in data
