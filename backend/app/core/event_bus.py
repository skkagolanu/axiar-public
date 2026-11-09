import asyncio
import json
import logging
import ssl
from typing import Any, Callable, Coroutine, Optional

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.errors import KafkaError

from app.core.config import settings
from app.core.events import DomainEvent

logger = logging.getLogger(__name__)

EventHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class EventBus:
    """Kafka-based event bus for domain events — producer + consumer lifecycle."""

    def __init__(self) -> None:
        self.producer: Optional[AIOKafkaProducer] = None
        self.consumers: dict[str, AIOKafkaConsumer] = {}
        self._consumer_tasks: list[asyncio.Task[None]] = []
        self._bootstrap_servers: list[str] = []
        self._subscriptions: dict[str, tuple[str, str, EventHandler]] = {}
        self._next_reconnect_attempt: float = 0.0

    def _connection_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"bootstrap_servers": self._bootstrap_servers}
        security_protocol = settings.KAFKA_SECURITY_PROTOCOL.upper()
        if security_protocol != "PLAINTEXT":
            kwargs["security_protocol"] = security_protocol
        ca_certificate = settings.KAFKA_SSL_CA_CERT.get_secret_value()
        if security_protocol in {"SSL", "SASL_SSL"} and ca_certificate:
            kwargs["ssl_context"] = ssl.create_default_context(cadata=ca_certificate)
        if security_protocol in {"SASL_PLAINTEXT", "SASL_SSL"}:
            kwargs.update(
                sasl_mechanism=settings.KAFKA_SASL_MECHANISM,
                sasl_plain_username=settings.KAFKA_SASL_USERNAME,
                sasl_plain_password=settings.KAFKA_SASL_PASSWORD.get_secret_value(),
            )
        return kwargs

    async def start(self) -> None:
        """Initialize Kafka producer. Consumers are registered via subscribe() after this."""
        if settings.DEMO_MODE:
            logger.info("Event bus disabled; using the demo no-op adapter")
            return
        configured_servers = [s.strip() for s in settings.KAFKA_BOOTSTRAP_SERVERS.split(",") if s.strip()]
        if not configured_servers:
            logger.info("Kafka is not configured; event bus disabled")
            return

        producer: Optional[AIOKafkaProducer] = None
        try:
            self._bootstrap_servers = configured_servers
            self.producer = AIOKafkaProducer(
                **self._connection_kwargs(),
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
            producer = self.producer
            await self.producer.start()
            logger.info("Event bus started")
        except Exception as e:
            logger.error(f"Failed to start event bus: {e}")
            if producer is not None:
                try:
                    await producer.stop()
                except Exception:
                    pass
            self.producer = None
            self._bootstrap_servers = []

    async def subscribe(self, topic: str, group_id: str, handler: EventHandler) -> None:
        """Start a background consumer for *topic* that dispatches each message to *handler*.

        Degrades gracefully: if Kafka is unavailable the consumer task logs and exits
        without crashing the application. A topic can only have one consumer per call —
        call subscribe() multiple times with distinct group_ids for fan-out.
        """
        key = f"{group_id}:{topic}"
        self._subscriptions[key] = (topic, group_id, handler)
        if key in self.consumers:
            return
        if not self._bootstrap_servers:
            logger.warning("Event bus not started — skipping consumer subscription for %s", topic)
            return

        consumer = AIOKafkaConsumer(
            topic,
            **self._connection_kwargs(),
            group_id=group_id,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            auto_offset_reset="earliest",
        )
        self.consumers[key] = consumer

        async def _run() -> None:
            try:
                await consumer.start()
                logger.info("Consumer started: topic=%s group=%s", topic, group_id)
                async for msg in consumer:
                    try:
                        await handler(msg.value)
                    except Exception as exc:
                        logger.exception("Consumer handler error on %s: %s", topic, exc)
            except KafkaError as e:
                logger.error("Consumer failed to start for %s: %s", topic, e)
            finally:
                try:
                    await consumer.stop()
                except Exception:
                    pass
                if self.consumers.get(key) is consumer:
                    self.consumers.pop(key, None)

        task = asyncio.create_task(_run(), name=f"consumer:{group_id}:{topic}")
        self._consumer_tasks = [previous for previous in self._consumer_tasks if not previous.done()]
        self._consumer_tasks.append(task)

    async def ensure_connected(self) -> None:
        """Retry a failed startup from the relay, preserving registered consumers."""
        if self.producer is None:
            now = asyncio.get_running_loop().time()
            if now < self._next_reconnect_attempt:
                return
            self._next_reconnect_attempt = now + 5
            await self.start()
        if self.producer is not None:
            for topic, group_id, handler in list(self._subscriptions.values()):
                await self.subscribe(topic, group_id, handler)

    async def stop(self) -> None:
        """Stop Kafka producer and all running consumers."""
        if self.producer:
            await self.producer.stop()
            self.producer = None
        for task in self._consumer_tasks:
            task.cancel()
        if self._consumer_tasks:
            await asyncio.gather(*self._consumer_tasks, return_exceptions=True)
        for consumer in self.consumers.values():
            try:
                await consumer.stop()
            except Exception:
                pass
        self.consumers.clear()
        self._consumer_tasks.clear()
        logger.info("Event bus stopped")

    async def publish(self, event: DomainEvent) -> None:
        """Publish domain event to Kafka."""
        if not self.producer:
            logger.warning(f"Event bus not available, skipping event: {event.event_type}")
            return

        topic = f"axiar.{event.aggregate_type}.events"

        try:
            # send() enqueues to the producer's local buffer and returns; we do NOT
            # send_and_wait (which blocks the request on a broker round-trip). Delivery is
            # best-effort/async — request correctness must never depend on it.
            await self.producer.send(
                topic,
                value={
                    "event_id": str(event.event_id),
                    "event_type": event.event_type,
                    "aggregate_id": str(event.aggregate_id),
                    "aggregate_type": event.aggregate_type,
                    "tenant_id": str(event.tenant_id) if event.tenant_id else None,
                    "occurred_at": event.occurred_at.isoformat(),
                    "data": event.data,
                },
            )
            logger.info(f"Published event: {event.event_type} for {event.aggregate_id}")
        except KafkaError as e:
            logger.error(f"Failed to publish event {event.event_type}: {e}")


event_bus = EventBus()
