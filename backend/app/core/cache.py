import json
import logging
import pickle
from typing import Any, Optional, cast

import redis.asyncio as redis
from redis.asyncio.cluster import ClusterNode, RedisCluster

from .config import settings

logger = logging.getLogger(__name__)


class CacheManager:
    def __init__(self) -> None:
        self.redis: Optional[Any] = None
        self.is_cluster = False

    async def init(self) -> None:
        """Initialize Redis connection (cluster or standalone)"""
        if settings.DEMO_MODE or not settings.REDIS_URL:
            self.redis = None
            self.is_cluster = False
            logger.info("Cache disabled; using the demo no-op adapter")
            return
        try:
            # Try cluster mode first
            if "," in settings.REDIS_URL or settings.REDIS_URL.startswith("redis-cluster://"):
                nodes = self._parse_cluster_nodes(settings.REDIS_URL)
                self.redis = RedisCluster(
                    startup_nodes=nodes,
                    decode_responses=False,
                    require_full_coverage=False,
                )
                self.is_cluster = True
                logger.info("Redis cluster initialized")
            else:
                # Fallback to standalone
                self.redis = redis.from_url(settings.REDIS_URL, decode_responses=False)
                self.is_cluster = False
                logger.info("Redis standalone initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Redis: {e}")
            # Fallback to standalone
            self.redis = redis.from_url(settings.REDIS_URL, decode_responses=False)
            self.is_cluster = False

    def _parse_cluster_nodes(self, url: str) -> list[ClusterNode]:
        """Parse cluster nodes from URL"""
        # Format: redis-cluster://host1:port1,host2:port2,host3:port3
        url = url.replace("redis-cluster://", "").replace("redis://", "")
        nodes = []
        for node in url.split(","):
            if ":" in node:
                host, port = node.split(":")
                nodes.append(ClusterNode(host, int(port)))
        return nodes if nodes else [ClusterNode("localhost", 6379)]

    async def get(self, key: str, default: Any = None) -> Any:
        """Get value from cache with automatic deserialization"""
        if not self.redis:
            return default

        try:
            value = await self.redis.get(key)
            if value is None:
                return default

            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return pickle.loads(value)
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return default

    async def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """Set value in cache with automatic serialization"""
        if not self.redis:
            return False

        try:
            try:
                serialized: Any = json.dumps(value, default=str)
            except (TypeError, ValueError):
                serialized = pickle.dumps(value)

            result = await self.redis.setex(key, ttl, serialized)
            return bool(result)
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete key from cache"""
        if not self.redis:
            return False

        try:
            return bool(await self.redis.delete(key))
        except Exception as e:
            logger.error(f"Cache delete error: {e}")
            return False

    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all keys matching pattern"""
        if not self.redis:
            return 0

        try:
            if self.is_cluster:
                # Cluster mode: scan all nodes (cast avoids mypy union narrowing)
                cluster: Any = cast(Any, self.redis)
                count = 0
                for node in cluster.get_nodes():
                    async for key in node.scan_iter(match=pattern):
                        await cluster.delete(key)
                        count += 1
                return count
            else:
                # Standalone mode — SCAN (non-blocking) rather than KEYS (which blocks Redis
                # while it walks the entire keyspace).
                count = 0
                async for key in self.redis.scan_iter(match=pattern, count=100):
                    await self.redis.delete(key)
                    count += 1
                return count
        except Exception as e:
            logger.error(f"Cache invalidate error: {e}")
            return 0

    async def health_check(self) -> bool:
        """Return True if the Redis backend responds to PING, False otherwise."""
        if not self.redis:
            return False
        try:
            result: Any = await self.redis.ping()
            return bool(result)
        except Exception as e:
            logger.error(f"Cache health check failed: {e}")
            return False

    async def close(self) -> None:
        """Close Redis connection"""
        if self.redis:
            await self.redis.close()


cache_manager = CacheManager()
