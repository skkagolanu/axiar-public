from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core.cache import CacheManager
from app.core.config import settings
from app.core.jwt_bearer import JWTBearer
from app.core.security import security_manager


def bearer_request(token=None):
    headers = [(b"authorization", f"Bearer {token}".encode())] if token else []
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


@pytest.mark.asyncio
async def test_cluster_uses_supported_node_objects_and_options(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "REDIS_URL", "redis-cluster://node-a:6379,node-b:6380")
    # Wrap the real constructor: an invalid argument or dict node must fail.
    from redis.asyncio.cluster import RedisCluster

    with patch("app.core.cache.RedisCluster", wraps=RedisCluster) as constructor:
        cache = CacheManager()
        await cache.init()
    assert cache.is_cluster
    assert [(n.host, n.port) for n in constructor.call_args.kwargs["startup_nodes"]] == [("node-a", 6379), ("node-b", 6380)]
    assert constructor.call_args.kwargs["require_full_coverage"] is False
    await cache.close()


@pytest.mark.asyncio
async def test_jwt_bearer_rejects_refresh_and_revoked_access_tokens():
    bearer = JWTBearer()
    with patch.object(bearer, "_is_revoked", AsyncMock(return_value=False)):
        with pytest.raises(HTTPException) as error:
            await bearer(bearer_request(security_manager.create_refresh_token("user")))
        assert error.value.status_code == 403
        token = security_manager.create_access_token({"sub": "user"})
        assert await bearer(bearer_request(token)) == token
    with patch.object(bearer, "_is_revoked", AsyncMock(return_value=True)):
        with pytest.raises(HTTPException) as error:
            await bearer(bearer_request(token))
        assert error.value.detail == "Token has been revoked"


@pytest.mark.asyncio
async def test_optional_jwt_bearer_accepts_missing_credentials():
    assert await JWTBearer(auto_error=False)(bearer_request()) is None
