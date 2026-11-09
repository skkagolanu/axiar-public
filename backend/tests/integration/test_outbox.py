"""Transactional outbox: booking events must survive Kafka downtime.

The test environment runs without Kafka (``event_bus.producer is None``) — which is
exactly the failure mode the outbox exists for: the fire-and-forget publish no-ops,
but the same DB transaction that persists the booking also persists an outbox row,
and the relay publishes it once Kafka returns.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.consumers.outbox_relay import relay_once
from app.core.event_bus import event_bus
from app.core.outbox import OutboxMessage
from app.core.tenant_context import set_current_tenant
from app.domain.booking.repository import BookingRepository


async def _insert_outbox_row(db_session, tenant_id) -> OutboxMessage:
    from uuid import uuid4

    row = OutboxMessage(
        tenant_id=tenant_id,
        aggregate_type="booking",
        aggregate_id=uuid4(),
        event_type="booking.created",
        payload={"probe": "outbox"},
    )
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    return row


@pytest.mark.integration
async def test_booking_create_writes_outbox_row_while_kafka_down(
    db_session, default_tenant_id, test_customer, test_provider, test_service
):
    """The write path must persist the event durably even though Kafka is absent."""
    assert event_bus.producer is None, "test env is expected to run without Kafka"

    set_current_tenant(default_tenant_id)
    try:
        repo = BookingRepository(db_session)
        booking = await repo.create(
            customer_id=test_customer,
            provider_id=test_provider,
            service_id=test_service,
            scheduled_time=datetime.now(timezone.utc) + timedelta(days=2),
            duration_minutes=60,
            location_postcode="NG7 2RD",
            base_price_cents=5000,
        )
        await db_session.commit()
    finally:
        set_current_tenant(None)

    result = await db_session.execute(select(OutboxMessage).where(OutboxMessage.aggregate_id == booking.id))
    rows = list(result.scalars().all())
    assert len(rows) == 1
    row = rows[0]
    assert row.status == "pending"
    assert row.event_type == "booking.created"
    assert row.tenant_id == default_tenant_id
    assert row.payload["provider_id"] == str(test_provider)


@pytest.mark.integration
async def test_relay_leaves_messages_pending_while_kafka_down(db_session, default_tenant_id):
    """With no producer, the relay must NOT mark messages published (no silent loss)."""
    assert event_bus.producer is None
    row = await _insert_outbox_row(db_session, default_tenant_id)
    row_id = row.id  # capture before expire_all() -- row itself becomes unsafe to touch after

    published = await relay_once()

    assert published == 0
    db_session.expire_all()
    refreshed = (await db_session.execute(select(OutboxMessage).where(OutboxMessage.id == row_id))).scalar_one()
    assert refreshed.status == "pending"
    assert refreshed.attempts == 0
    assert refreshed.published_at is None


@pytest.mark.integration
async def test_relay_publishes_pending_messages_when_kafka_returns(db_session, default_tenant_id, monkeypatch):
    """Once a producer is available, the relay publishes the backlog and marks it."""
    row = await _insert_outbox_row(db_session, default_tenant_id)
    row_id = row.id  # capture before expire_all() -- row itself becomes unsafe to touch after

    fake_producer = AsyncMock()
    acknowledged = asyncio.get_running_loop().create_future()
    acknowledged.set_result(None)
    fake_producer.send.return_value = acknowledged
    monkeypatch.setattr(event_bus, "producer", fake_producer)

    published = await relay_once()

    assert published >= 1
    fake_producer.send.assert_any_await("axiar.booking.events", row.to_kafka_message())
    db_session.expire_all()
    refreshed = (await db_session.execute(select(OutboxMessage).where(OutboxMessage.id == row_id))).scalar_one()
    assert refreshed.status == "published"
    assert refreshed.published_at is not None


@pytest.mark.integration
async def test_relay_waits_for_broker_ack(db_session, default_tenant_id, monkeypatch):
    row = await _insert_outbox_row(db_session, default_tenant_id)
    row_id = row.id
    entered = asyncio.Event()
    acknowledged = asyncio.get_running_loop().create_future()

    async def delayed_ack(*args):
        entered.set()
        return acknowledged

    fake = AsyncMock()
    fake.send.side_effect = delayed_ack
    monkeypatch.setattr(event_bus, "producer", fake)
    task = asyncio.create_task(relay_once())
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        db_session.expire_all()
        current = (await db_session.execute(select(OutboxMessage).where(OutboxMessage.id == row_id))).scalar_one()
        assert current.status == "pending"
        assert current.published_at is None
        assert not task.done()
    finally:
        acknowledged.set_result(None)
        await task


@pytest.mark.integration
async def test_transient_outage_does_not_exhaust_retries(db_session, default_tenant_id, monkeypatch):
    from aiokafka.errors import KafkaTimeoutError

    row = await _insert_outbox_row(db_session, default_tenant_id)
    row_id = row.id
    fake = AsyncMock()
    fake.send.side_effect = KafkaTimeoutError("broker unavailable")
    monkeypatch.setattr(event_bus, "producer", fake)
    for _ in range(6):
        assert await relay_once() == 0
    db_session.expire_all()
    current = (await db_session.execute(select(OutboxMessage).where(OutboxMessage.id == row_id))).scalar_one()
    assert current.status == "pending"
    assert current.attempts == 6
    fake.send.side_effect = None
    acknowledged = asyncio.get_running_loop().create_future()
    acknowledged.set_result(None)
    fake.send.return_value = acknowledged
    assert await relay_once() == 1
    identities = {call.args[1]["event_id"] for call in fake.send.await_args_list}
    assert identities == {str(row_id)}
