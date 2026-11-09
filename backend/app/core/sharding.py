import hashlib
from typing import Optional
from uuid import UUID

from app.core.config import settings


class ShardRouter:
    """Route database operations to appropriate shard"""

    def __init__(self) -> None:
        self.shard_count = getattr(settings, "DATABASE_SHARD_COUNT", 1)
        self.shard_urls = self._parse_shard_urls()

    def _parse_shard_urls(self) -> dict[int, str]:
        """Parse shard URLs from config"""
        urls = {}
        base_url = settings.DATABASE_URL

        # If no sharding configured, use single database
        if self.shard_count == 1:
            return {0: base_url}

        # Parse shard URLs from environment
        # Format: DATABASE_SHARD_0_URL, DATABASE_SHARD_1_URL, etc.
        for i in range(self.shard_count):
            shard_url = getattr(settings, f"DATABASE_SHARD_{i}_URL", None)
            if shard_url:
                urls[i] = shard_url
            else:
                # Fallback: append shard suffix to base URL
                urls[i] = base_url.replace("/axiar", f"/axiar_shard_{i}")

        return urls

    def get_shard_id(self, tenant_id: UUID) -> int:
        """Get shard ID for tenant using consistent hashing"""
        if self.shard_count == 1:
            return 0

        # Consistent hashing on tenant_id — md5 is used as a fast non-cryptographic
        # hash for shard placement only (usedforsecurity=False keeps bandit/B324 happy).
        hash_value = int(hashlib.md5(str(tenant_id).encode(), usedforsecurity=False).hexdigest(), 16)
        return hash_value % self.shard_count

    def get_shard_url(self, tenant_id: UUID) -> str:
        """Get database URL for tenant's shard"""
        shard_id = self.get_shard_id(tenant_id)
        return self.shard_urls.get(shard_id, self.shard_urls[0])

    def get_all_shards(self) -> list[tuple[int, str]]:
        """Get all shard IDs and URLs"""
        return [(shard_id, url) for shard_id, url in self.shard_urls.items()]


shard_router = ShardRouter()
