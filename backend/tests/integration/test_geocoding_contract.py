import pytest

from app.core.config import settings
from app.main import app


@pytest.mark.asyncio
async def test_missing_geocoding_configuration_matches_documented_error(async_client, admin_token, monkeypatch):
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "GOOGLE_MAPS_API_KEY", "")
    response = await async_client.get(
        "/api/v1/providers/search/by-postcode",
        params={"postcode": "NG7 2RD"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 501
    assert "GOOGLE_MAPS_API_KEY" in response.json()["detail"]
    operation = app.openapi()["paths"]["/api/v1/providers/search/by-postcode"]["get"]
    assert "501" in operation["responses"]
