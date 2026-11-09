import asyncio
import json
import logging
from asyncio import Task
from typing import Any, Dict, Optional, Set
from uuid import UUID

from fastapi import WebSocket

from app.core.cache import cache_manager

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Tracks local WebSocket connections and fans messages out across workers via Redis.

    Each worker holds only its own sockets in `active_connections`. Sends are published to a
    shared Redis channel; every worker's listener delivers to whichever recipients it holds
    locally. If Redis is unavailable it degrades to local-only delivery.
    """

    CHANNEL = "ws:broadcast"
    STARTUP_TIMEOUT_SECONDS = 5.0
    CLOSE_TIMEOUT_SECONDS = 1.0

    def __init__(self) -> None:
        self.active_connections: Dict[UUID, Set[WebSocket]] = {}
        self._pubsub: Any = None
        self._listener_task: Optional[Task[None]] = None

    async def start(self) -> None:
        """Subscribe to the cross-worker broadcast channel. Call from the app lifespan."""
        if cache_manager.redis is None:
            logger.info("WebSocket backplane disabled (no Redis); local-only delivery")
            return
        try:
            if hasattr(cache_manager.redis, "pubsub"):
                self._pubsub = cache_manager.redis.pubsub()
            else:
                logger.info("WebSocket backplane disabled (no pubsub support)")
                return
            # Upstash can accept the TLS connection but stall during SUBSCRIBE. Lifespan
            # must still complete so Render can serve health checks; the backplane is an
            # optional cross-worker optimization and already degrades to local delivery.
            await asyncio.wait_for(
                self._pubsub.subscribe(self.CHANNEL),
                timeout=self.STARTUP_TIMEOUT_SECONDS,
            )
            self._listener_task = asyncio.create_task(self._listen())
            logger.info("WebSocket Redis backplane started")
        except Exception as e:
            logger.error(f"WebSocket backplane unavailable: {e}")
            pubsub = self._pubsub
            self._pubsub = None
            self._listener_task = None
            if pubsub is not None:
                try:
                    await asyncio.wait_for(pubsub.aclose(), timeout=self.CLOSE_TIMEOUT_SECONDS)
                except Exception:
                    pass

    async def stop(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
        if self._pubsub:
            try:
                await self._pubsub.unsubscribe(self.CHANNEL)
                await self._pubsub.aclose()
            except Exception:
                pass

    async def _listen(self) -> None:
        try:
            if self._pubsub is None:
                return
            async for msg in self._pubsub.listen():
                if msg.get("type") != "message":
                    continue
                try:
                    payload = json.loads(msg["data"])
                    user_id = UUID(payload["user_id"])
                except Exception:
                    continue
                await self._deliver_local(user_id, payload["message"])
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"WebSocket backplane listener stopped: {e}")

    async def connect(self, user_id: UUID, websocket: WebSocket, subprotocol: Optional[str] = None) -> None:
        await websocket.accept(subprotocol=subprotocol)
        self.active_connections.setdefault(user_id, set()).add(websocket)

    def disconnect(self, user_id: UUID, websocket: WebSocket) -> None:
        if user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

    async def _deliver_local(self, user_id: UUID, message: Dict[str, Any]) -> None:
        for connection in self.active_connections.get(user_id, set()):
            try:
                await connection.send_json(message)
            except Exception:
                pass

    async def send_personal_message(self, message: Dict[str, Any], user_id: UUID) -> None:
        # Publish to all workers; each delivers to its local sockets. Fall back to local-only
        # delivery if Redis is unavailable.
        if cache_manager.redis is not None:
            try:
                if hasattr(cache_manager.redis, "publish"):
                    await cache_manager.redis.publish(self.CHANNEL, json.dumps({"user_id": str(user_id), "message": message}))
                    return
                else:
                    logger.info("WebSocket publish not supported (non-pubsub Redis)")
            except Exception as e:
                logger.error(f"WebSocket publish failed, delivering locally: {e}")
        await self._deliver_local(user_id, message)

    async def broadcast_to_booking(
        self, message: Dict[str, Any], customer_id: UUID, provider_id: UUID, agent_id: Optional[UUID] = None
    ) -> None:
        recipients = [customer_id, provider_id]
        if agent_id:
            recipients.append(agent_id)
        for user_id in recipients:
            await self.send_personal_message(message, user_id)


manager = ConnectionManager()
