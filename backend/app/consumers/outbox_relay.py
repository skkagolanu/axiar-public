import asyncio
import logging
from datetime import datetime, timezone

from aiokafka.errors import KafkaError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import db_manager
from app.core.event_bus import event_bus
from app.core.outbox import OutboxMessage

logger = logging.getLogger(__name__)

# Bound the in-flight relay batch while allowing concurrent broker acknowledgements.
BATCH_SIZE = 500
POLL_INTERVAL = 0.25
MAX_ATTEMPTS = 5


async def relay_once() -> int:
    """Run a single relay pass: claim pending messages and publish them to Kafka.

    Returns the number of messages successfully published. When Kafka is
    unavailable (no producer), claimed messages are left in ``pending`` so a
    later pass retries them — durability is the whole point of the outbox.
    """
    published = 0
    async with db_manager.get_session() as session:
        messages = await _claim_batch(session)
        deliveries = []
        for msg in messages:
            if event_bus.producer is None:
                # Kafka down — leave the batch pending and retry next pass.
                break
            try:
                topic = f"axiar.{msg.aggregate_type}.events"
                # Queue the bounded batch so Kafka can combine records. Each returned
                # delivery future is still awaited before its row can be published.
                delivery = await event_bus.producer.send(topic, msg.to_kafka_message())
                deliveries.append((msg, delivery))
            except Exception as e:
                _record_failure(msg, e)
        for msg, delivery in deliveries:
            try:
                await delivery
                msg.status = "published"
                msg.published_at = datetime.now(timezone.utc)
                published += 1
            except Exception as e:
                _record_failure(msg, e)
        await session.commit()
    return published


def _record_failure(msg: OutboxMessage, error: Exception) -> None:
    msg.attempts += 1
    msg.last_error = str(error)[:1000]
    if msg.attempts >= MAX_ATTEMPTS and not isinstance(error, (KafkaError, TimeoutError)):
        msg.status = "failed"
    logger.warning("Outbox relay failed for %s: %s", msg.id, error)


async def relay_outbox():
    """Background loop: poll the outbox and publish pending messages forever."""
    while True:
        try:
            await event_bus.ensure_connected()
            await relay_once()
        except Exception as e:
            logger.error(f"Outbox relay error: {e}")
        await asyncio.sleep(POLL_INTERVAL)


async def _claim_batch(session: AsyncSession) -> list[OutboxMessage]:
    stmt = (
        select(OutboxMessage)
        .where(OutboxMessage.status == "pending")
        .order_by(OutboxMessage.created_at.asc())
        .limit(BATCH_SIZE)
        .with_for_update(skip_locked=True)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
