'Unit tests for get_current_user_ws: the JWT must be accepted.'

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from starlette.datastructures import Headers

from app.api.dependencies.auth import get_current_user_ws
from app.core.security import security_manager
from app.domain.user.models import User, UserRole


def _fake_websocket(headers: dict[str, str] | None = None) -> MagicMock:
    ws = MagicMock()
    ws.headers = Headers(headers or {})
    ws.close = AsyncMock()
    return ws


async def _make_user(db_session, test_tenant) -> User:
    user = User(
        id=uuid4(),
        tenant_id=test_tenant,
        email=f"ws-{uuid4().hex[:8]}@example.test",
        hashed_password=security_manager.hash_password("Password123!"),
        first_name="WS",
        last_name="User",
        role=UserRole.CUSTOMER,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_accepts_token_via_query_param(db_session, test_tenant):
    """Legacy path: ?token=<jwt> still works during the transition."""
    user = await _make_user(db_session, test_tenant)
    token = security_manager.create_access_token({"sub": str(user.id)})
    ws = _fake_websocket()

    result = await get_current_user_ws(ws, token=token)

    assert result is not None
    assert result.id == user.id
    ws.close.assert_not_called()


@pytest.mark.asyncio
async def test_accepts_token_via_subprotocol_header(db_session, test_tenant):
    """Preferred path: Sec-WebSocket-Protocol: access_token, <jwt> -- no query param at all."""
    user = await _make_user(db_session, test_tenant)
    token = security_manager.create_access_token({"sub": str(user.id)})
    ws = _fake_websocket({"sec-websocket-protocol": f"access_token, {token}"})

    result = await get_current_user_ws(ws, token=None)

    assert result is not None
    assert result.id == user.id
    ws.close.assert_not_called()


@pytest.mark.asyncio
async def test_query_param_takes_priority_over_header(db_session, test_tenant):
    """If both are somehow present, the explicit query param wins.

    Proven by making the two tokens resolve to different outcomes: the query
    token names a real user (so the call should succeed); the header token
    names a nonexistent one (so if the header were used instead, it would
    fail). Only a query-param-wins implementation makes this pass.
    """
    user = await _make_user(db_session, test_tenant)
    query_token = security_manager.create_access_token({"sub": str(user.id)})
    header_token = security_manager.create_access_token({"sub": str(uuid4())})
    ws = _fake_websocket({"sec-websocket-protocol": f"access_token, {header_token}"})

    result = await get_current_user_ws(ws, token=query_token)

    assert result is not None
    assert result.id == user.id
    ws.close.assert_not_called()


@pytest.mark.asyncio
async def test_closes_with_1008_when_no_token_offered_at_all():
    """Neither query param nor subprotocol header -- must not fall through to a crash."""
    ws = _fake_websocket()

    result = await get_current_user_ws(ws, token=None)

    assert result is None
    ws.close.assert_called_once_with(code=1008)


@pytest.mark.asyncio
async def test_ignores_subprotocol_header_missing_access_token_marker():
    """A Sec-WebSocket-Protocol header that isn't our convention must not be treated as a token."""
    ws = _fake_websocket({"sec-websocket-protocol": "graphql-ws"})

    result = await get_current_user_ws(ws, token=None)

    assert result is None
    ws.close.assert_called_once_with(code=1008)


@pytest.mark.asyncio
async def test_closes_with_1008_on_invalid_token():
    ws = _fake_websocket()

    result = await get_current_user_ws(ws, token="not-a-real-jwt")

    assert result is None
    ws.close.assert_called_once_with(code=1008)
