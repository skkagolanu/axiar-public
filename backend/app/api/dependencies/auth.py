import logging
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Query, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import bindparam, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import db_manager, get_db_session
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.security import security_manager
from app.core.tenant_context import get_current_tenant, set_current_tenant
from app.domain.user.models import User

logger = logging.getLogger(__name__)

security = HTTPBearer()
_USER_LOOKUP = select(User).where(User.id == bindparam("authenticated_user_id"))


class RoleBasedAccessControl:
    def __init__(self):
        self.permissions = {
            "admin": [
                "user:read",
                "user:write",
                "user:delete",
                "booking:read",
                "booking:write",
                "booking:delete",
                "provider:read",
                "provider:write",
                "provider:delete",
                "analytics:read",
                "system:admin",
            ],
            "provider": ["booking:read", "booking:write", "team:read", "team:write", "analytics:read", "profile:write"],
            "customer": ["booking:read", "booking:write", "profile:read", "profile:write"],
            "field_agent": ["booking:read", "booking:update_status", "profile:read"],
        }

    def has_permission(self, user_role: str, required_permission: str) -> bool:
        """Check if user role has required permission"""
        return required_permission in self.permissions.get(user_role, [])


rbac = RoleBasedAccessControl()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security), session: AsyncSession = Depends(get_db_session)
) -> User:
    """Get current authenticated user and enforce token-to-request tenant binding."""
    token = credentials.credentials

    # Verify token. expected_type="access" rejects refresh tokens (7-day lifetime) and
    # booking-scoped guest tokens, both signed with the same secret.
    payload = await security_manager.verify_token(token, expected_type="access")
    if not payload:
        raise AuthenticationError("Invalid authentication credentials")

    user_id = payload.get("sub")
    if not user_id:
        raise AuthenticationError("Invalid token payload")

    token_tenant_id = payload.get("tenant_id")
    request_tenant_id = get_current_tenant()

    if token_tenant_id:
        try:
            token_tenant_uuid = UUID(token_tenant_id)
        except ValueError:
            raise AuthenticationError("Invalid tenant claim in token")

        # The token's tenant must match the request's resolved tenant (from the
        # ``X-Tenant-ID`` / ``X-Tenant-Slug`` header). This prevents tokens issued for
        # one tenant from being replayed against another.
        if request_tenant_id and token_tenant_uuid != request_tenant_id:
            raise AuthenticationError("Tenant mismatch")

    # Load the user. For legacy/test tokens that do not contain a ``tenant_id`` claim,
    
    result = await session.execute(_USER_LOOKUP, {"authenticated_user_id": user_id})
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise AuthenticationError("User not found or inactive")

    if token_tenant_id:
        if user.tenant_id != token_tenant_uuid:
            raise AuthenticationError("Token tenant does not match user tenant")
        set_current_tenant(user.tenant_id)
    else:
        logger.warning("Legacy token without tenant_id for user %s; falling back to user.tenant_id", user_id)
        set_current_tenant(user.tenant_id)

    return user


def require_role(role):
    """Require specific user role(s)"""

    def dependency(current_user: User = Depends(get_current_user)):
        # Handle both string and list/enum inputs
        if isinstance(role, (list, tuple)):
            allowed_roles = [r.value if hasattr(r, "value") else r for r in role]
            user_role_value = current_user.role.value if hasattr(current_user.role, "value") else current_user.role
            if user_role_value not in allowed_roles:
                raise AuthorizationError("Insufficient permissions")
        else:
            role_value = role.value if hasattr(role, "value") else role
            user_role_value = current_user.role.value if hasattr(current_user.role, "value") else current_user.role
            if user_role_value != role_value:
                raise AuthorizationError("Insufficient permissions")
        return current_user

    return dependency


def require_permissions(*permissions: str):
    """Require specific permissions"""

    def dependency(current_user: User = Depends(get_current_user)):
        user_role = current_user.role
        for permission in permissions:
            if not rbac.has_permission(user_role, permission):
                raise AuthorizationError("Insufficient permissions")
        return current_user

    return dependency


async def get_current_provider_id(current_user: User = Depends(get_current_user)) -> str:
    """Get current provider ID"""
    if current_user.role != "provider":
        raise AuthorizationError("Provider role required")
    return str(current_user.id)


async def get_current_agent_id(current_user: User = Depends(get_current_user)) -> str:
    """Get current field agent ID"""
    if current_user.role != "field_agent":
        raise AuthorizationError("Field agent role required")
    return str(current_user.id)


async def get_current_user_ws(websocket: WebSocket, token: Optional[str] = Query(None)) -> Optional[User]:
    'Get current user from WebSocket token.'
    if not token:
        offered = [p.strip() for p in websocket.headers.get("sec-websocket-protocol", "").split(",")]
        if len(offered) >= 2 and offered[0] == "access_token":
            token = offered[1]

    if not token:
        await websocket.close(code=1008)
        return None

    try:
        payload = await security_manager.verify_token(token, expected_type="access")
        if not payload or not payload.get("sub"):
            await websocket.close(code=1008)
            return None

        user_id = UUID(payload["sub"])

        async with db_manager.get_session() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            # is_active mirrors get_current_user: a deactivated account must not hold
            # an open socket (it would keep receiving booking-status pushes).
            if not user or not user.is_active:
                await websocket.close(code=1008)
                return None
            set_current_tenant(user.tenant_id)
            return user
    except Exception:
        await websocket.close(code=1008)
        return None
