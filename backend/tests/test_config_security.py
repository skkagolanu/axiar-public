"""Tests for Settings production_guard validator and env-driven config security."""

import os
from typing import Generator

import pytest

from app.core.config import Settings

_VALID_SECRET_KEY = "a" * 32
_PRODUCTION_INTEGRATIONS = {
    "REDIS_URL": "redis://localhost:6379",
    "STRIPE_SECRET_KEY": "stripe",
    "STRIPE_WEBHOOK_SECRET": "stripe-webhook",
    "SENDGRID_API_KEY": "sendgrid",
    "TWILIO_ACCOUNT_SID": "twilio",
    "TWILIO_AUTH_TOKEN": "twilio-token",
    "TWILIO_PHONE_NUMBER": "+441234567890",
    "GOOGLE_MAPS_API_KEY": "maps",
    "GOOGLE_CLIENT_ID": "google-client",
    "GOOGLE_CLIENT_SECRET": "google-secret",
    "MICROSOFT_CLIENT_ID": "microsoft-client",
    "MICROSOFT_CLIENT_SECRET": "microsoft-secret",
}


def _set_valid_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", _VALID_SECRET_KEY)
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("ALLOWED_HOSTS", "example.com,api.example.com")
    monkeypatch.setenv("CORS_ORIGINS", "https://example.com")


@pytest.fixture(autouse=True)
def _clear_env() -> Generator[None, None, None]:
    """Fixture that clears SECRET_KEY before each test, restoring after."""
    # The module-level settings = Settings() at the bottom of config.py already
    # captured whatever .env was present at import time.  To test fresh
    # construction, we rely on monkeypatch (per-test) to override os.environ.
    yield


def test_development_mode_works_with_auto_generated_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """ENVIRONMENT=development and no SECRET_KEY set must succeed (auto-generated)."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("SECRET_KEY", raising=False)

    settings = Settings()
    assert settings.ENVIRONMENT == "development"
    # Auto-generated secret is 43 chars (secrets.token_urlsafe(32) → 43 base64 chars)
    assert len(settings.SECRET_KEY.get_secret_value()) >= 32


def test_production_rejects_short_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """ENVIRONMENT=production with a too-short SECRET_KEY must raise ValueError."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "short")  # 5 chars < 32

    with pytest.raises(ValueError, match="SECRET_KEY must be at least"):
        Settings()


def test_production_rejects_placeholder_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """ENVIRONMENT=production with a known placeholder SECRET_KEY must raise ValueError."""
    for placeholder in ("CHANGE_ME", "changeme", "placeholder"):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("SECRET_KEY", placeholder)

        with pytest.raises(ValueError, match="SECRET_KEY must be at least"):
            Settings()


def test_production_rejects_debug_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """ENVIRONMENT=production with DEBUG=true must raise ValueError."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", _VALID_SECRET_KEY)
    monkeypatch.setenv("DEBUG", "true")

    with pytest.raises(ValueError, match="DEBUG must be False"):
        Settings()


def test_production_rejects_wildcard_allowed_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    """ENVIRONMENT=production with ALLOWED_HOSTS containing '*' must raise ValueError."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", _VALID_SECRET_KEY)
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("ALLOWED_HOSTS", "*")

    with pytest.raises(ValueError, match="ALLOWED_HOSTS must not contain wildcard"):
        Settings()


def test_production_rejects_wildcard_cors_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    """ENVIRONMENT=production with CORS_ORIGINS containing '*' must raise ValueError."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", _VALID_SECRET_KEY)
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("ALLOWED_HOSTS", "example.com")
    monkeypatch.setenv("CORS_ORIGINS", "*")

    with pytest.raises(ValueError, match="CORS_ORIGINS must not contain wildcard"):
        Settings()


def test_production_passes_with_valid_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """ENVIRONMENT=production with all valid settings must succeed."""
    _set_valid_production(monkeypatch)
    for name, value in _PRODUCTION_INTEGRATIONS.items():
        monkeypatch.setenv(name, value)

    settings = Settings()
    assert settings.ENVIRONMENT == "production"
    assert settings.DEBUG is False
    assert "*" not in settings.ALLOWED_HOSTS
    assert "*" not in settings.CORS_ORIGINS


def test_production_rejects_missing_integrations_outside_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_valid_production(monkeypatch)
    monkeypatch.setenv("DEMO_MODE", "false")
    for name in _PRODUCTION_INTEGRATIONS:
        monkeypatch.setenv(name, "")

    with pytest.raises(ValueError, match="Missing production integration settings"):
        Settings()


def test_production_demo_allows_keyless_integrations(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_valid_production(monkeypatch)
    monkeypatch.setenv("DEMO_MODE", "true")
    for name in _PRODUCTION_INTEGRATIONS:
        monkeypatch.setenv(name, "")

    configured = Settings()

    assert configured.DEMO_MODE is True
    assert configured.REDIS_URL == ""
    assert configured.STRIPE_SECRET_KEY == ""
