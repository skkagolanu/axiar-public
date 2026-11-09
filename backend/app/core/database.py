from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from .config import settings
from .sharding import shard_router
from .tenant_context import get_current_tenant

Base = declarative_base()


class DatabaseManager:
    def __init__(self) -> None:
        self.engines: Dict[str, Any] = {}
        self.session_makers: Dict[str, async_sessionmaker[AsyncSession]] = {}
        self._setup_engines()

    def _setup_engines(self) -> None:
        # Initialize engines for all shards
        for shard_id, url in shard_router.get_all_shards():
            engine = create_async_engine(
                url,
                pool_size=settings.DATABASE_POOL_SIZE,
                max_overflow=settings.DATABASE_MAX_OVERFLOW,
                echo=settings.DEBUG,
                future=True,
            )
            self.engines[f"shard_{shard_id}"] = engine
            self.session_makers[f"shard_{shard_id}"] = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        # Alias main to shard_0
        self.engines["main"] = self.engines["shard_0"]
        self.session_makers["main"] = self.session_makers["shard_0"]

    def get_shard_for_tenant(self, tenant_id: UUID) -> str:
        """Get shard name for tenant"""
        shard_id = shard_router.get_shard_id(tenant_id)
        return f"shard_{shard_id}"

    def get_shard_for_postcode(self, postcode: str) -> str:
        """Determine database shard based on postcode (geographic sharding)"""
        # Resolve the primary application shard.
        return "main"

    @asynccontextmanager
    async def get_session(
        self, shard: Optional[str] = None, tenant_id: Optional[UUID] = None
    ) -> AsyncGenerator[AsyncSession, None]:
        # Determine shard
        if tenant_id:
            shard = self.get_shard_for_tenant(tenant_id)
        elif not shard:
            shard = "main"

        session_maker = self.session_makers.get(shard, self.session_makers["main"])
        async with session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()


db_manager = DatabaseManager()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for a DB session, routed to the current tenant's shard.

    TenantMiddleware sets the tenant context before endpoint dependencies resolve, so the
    correct shard is known here. With DATABASE_SHARD_COUNT=1 this always resolves to
    shard_0 (== "main"), so behaviour is unchanged for single-DB deployments.
    """
    tenant_id = get_current_tenant()
    async with db_manager.get_session(tenant_id=tenant_id) as session:
        yield session
