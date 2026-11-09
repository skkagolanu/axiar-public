"""Sentry init: must no-op cleanly without a DSN and initialize when set."""

import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr

from app.core import observability


def test_init_sentry_noop_when_dsn_unset(monkeypatch):
    monkeypatch.setattr(observability.settings, "SENTRY_DSN", None)
    assert observability.init_sentry() is False


def test_init_sentry_initializes_when_dsn_set(monkeypatch):
    monkeypatch.setattr(observability.settings, "SENTRY_DSN", SecretStr("https://fixture-30b069010a93@example.test/1"))
    monkeypatch.setattr(observability.settings, "ENVIRONMENT", "staging")
    monkeypatch.setattr(observability.settings, "SENTRY_TRACES_SAMPLE_RATE", 0.25)

    fake_sentry_sdk = ModuleType("sentry_sdk")
    fake_sentry_sdk.init = MagicMock()
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sentry_sdk)

    assert observability.init_sentry() is True
    fake_sentry_sdk.init.assert_called_once_with(
        dsn="https://fixture-30b069010a93@example.test/1",
        environment="staging",
        traces_sample_rate=0.25,
    )


def test_init_sentry_degrades_when_sdk_not_installed(monkeypatch):
    monkeypatch.setattr(observability.settings, "SENTRY_DSN", SecretStr("https://fixture-30b069010a93@example.test/1"))
    monkeypatch.setitem(sys.modules, "sentry_sdk", None)  # forces ImportError on `import sentry_sdk`

    assert observability.init_sentry() is False


def test_flush_sentry_noop_when_not_initialized(monkeypatch):
    fake_sentry_sdk = ModuleType("sentry_sdk")
    fake_sentry_sdk.flush = MagicMock()
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sentry_sdk)

    observability.flush_sentry(False)

    fake_sentry_sdk.flush.assert_not_called()


def test_flush_sentry_calls_flush_when_initialized(monkeypatch):
    fake_sentry_sdk = ModuleType("sentry_sdk")
    fake_sentry_sdk.flush = MagicMock()
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sentry_sdk)

    observability.flush_sentry(True)

    fake_sentry_sdk.flush.assert_called_once()
