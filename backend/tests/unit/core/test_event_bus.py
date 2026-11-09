from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.core.event_bus import EventBus


@pytest.mark.asyncio
async def test_managed_kafka_uses_sasl_ssl(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "KAFKA_BOOTSTRAP_SERVERS", "broker.example.com:28474")
    monkeypatch.setattr(settings, "KAFKA_SECURITY_PROTOCOL", "SASL_SSL")
    monkeypatch.setattr(settings, "KAFKA_SASL_MECHANISM", "SCRAM-SHA-256")
    monkeypatch.setattr(settings, "KAFKA_SASL_USERNAME", "axiar")
    monkeypatch.setattr(settings, "KAFKA_SASL_PASSWORD", settings.KAFKA_SASL_PASSWORD.__class__("secret"))
    monkeypatch.setattr(settings, "KAFKA_SSL_CA_CERT", settings.KAFKA_SSL_CA_CERT.__class__(""))

    producer = AsyncMock()
    with patch("app.core.event_bus.AIOKafkaProducer", return_value=producer) as producer_class:
        bus = EventBus()
        await bus.start()

    producer_class.assert_called_once()
    connection = producer_class.call_args.kwargs
    assert connection["bootstrap_servers"] == ["broker.example.com:28474"]
    assert connection["security_protocol"] == "SASL_SSL"
    assert connection["sasl_mechanism"] == "SCRAM-SHA-256"
    assert connection["sasl_plain_username"] == "axiar"
    assert connection["sasl_plain_password"] == "secret"
    producer.start.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_kafka_start_disables_consumer_retries(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "KAFKA_BOOTSTRAP_SERVERS", "unavailable:9092")
    producer = AsyncMock()
    producer.start.side_effect = RuntimeError("unavailable")

    with patch("app.core.event_bus.AIOKafkaProducer", return_value=producer):
        bus = EventBus()
        await bus.start()
        await bus.subscribe("axiar.booking.events", "test", AsyncMock())

    assert bus.producer is None
    assert bus.consumers == {}
    producer.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_demo_event_bus_never_constructs_kafka(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    monkeypatch.setattr(settings, "KAFKA_BOOTSTRAP_SERVERS", "broker.example.com:9092")

    with patch("app.core.event_bus.AIOKafkaProducer") as producer_class:
        bus = EventBus()
        await bus.start()

    producer_class.assert_not_called()
    assert bus.producer is None
