import hashlib
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.security.base import SecurityBase

from app.core.cache import cache_manager
from app.core.config import settings
from app.core.security import security_manager


class JWTBearer(SecurityBase):
    """Enhanced JWT Bearer with validation and a Redis-backed revocation list.

    The blacklist lives in Redis (not an in-process set) so revocation is shared across all
    workers and survives restarts.
    """

    def __init__(self, auto_error: bool = True):
        self._bearer = HTTPBearer(auto_error=auto_error)
        self.model = self._bearer.model
        self.scheme_name = self._bearer.scheme_name
        self.auto_error = auto_error

    @staticmethod
    def _key(token: str) -> str:
        # Store a hash, never the raw token.
        return f"jwt:blacklist:{hashlib.sha256(token.encode()).hexdigest()}"

    async def _is_revoked(self, token: str) -> bool:
        return bool(await cache_manager.get(self._key(token)))

    async def __call__(self, request: Request) -> Optional[str]:
        credentials: Optional[HTTPAuthorizationCredentials] = await self._bearer(request)

        if credentials:
            if not credentials.scheme == "Bearer":
                raise HTTPException(status_code=403, detail="Invalid authentication scheme")

            token: str = credentials.credentials

            if await self._is_revoked(token):
                raise HTTPException(status_code=403, detail="Token has been revoked")

            payload = await security_manager.verify_token(token, expected_type="access")
            if not payload:
                raise HTTPException(status_code=403, detail="Invalid or expired token")

            request.state.user_id = payload.get("sub")
            request.state.token_payload = payload

            return token
        else:
            if not self.auto_error:
                return None
            raise HTTPException(status_code=403, detail="Invalid authorization code")

    async def revoke_token(self, token: str) -> None:
        """Revoke a token by adding its hash to the Redis blacklist.

        TTL matches the access-token lifetime, so the entry expires when the token would.
        """
        ttl = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        await cache_manager.set(self._key(token), "1", ttl=ttl)


jwt_bearer = JWTBearer()
