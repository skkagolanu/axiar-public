import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher

from .config import settings


class SecurityManager:
    def __init__(self) -> None:
        self.password_hash = PasswordHash((BcryptHasher(rounds=12),))
        self.secret_key = settings.SECRET_KEY.get_secret_value()
        self.algorithm = settings.JWT_ALGORITHM

    def hash_password(self, password: str) -> str:
        """Hash password with bcrypt"""
        hashed_password: str = self.password_hash.hash(password)
        return hashed_password

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify password against hash"""
        is_valid: bool = self.password_hash.verify(plain_password, hashed_password)
        return is_valid

    def create_access_token(
        self,
        data: Dict[str, Any],
        expires_delta: Optional[timedelta] = None,
        extra_claims: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create JWT access token.

        ``extra_claims`` is merged into the encoded payload so callers can pass
        tenant-scoped binding without mutating the caller's ``data`` dict.
        """
        to_encode = data.copy()

        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

        to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc), "type": "access"})

        if extra_claims:
            to_encode.update(extra_claims)

        token: str = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return token

    def create_refresh_token(
        self,
        user_id: str,
        tenant_id: Optional[str] = None,
    ) -> str:
        """Create JWT refresh token.

        ``tenant_id`` is bound when available so refresh-token rotation can be
        validated against the request tenant.
        """
        to_encode: Dict[str, Any] = {
            "sub": user_id,
            "type": "refresh",
            "exp": datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            "iat": datetime.now(timezone.utc),
        }

        if tenant_id:
            to_encode["tenant_id"] = tenant_id

        token: str = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return token

    async def verify_token(self, token: str, expected_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        'Verify and decode a JWT.'
        try:
            payload: Dict[str, Any] = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])

            exp = payload.get("exp")
            if exp and datetime.now(timezone.utc) > datetime.fromtimestamp(exp, tz=timezone.utc):
                return None

            if expected_type is not None and payload.get("type") != expected_type:
                return None

            return payload
        except InvalidTokenError:
            return None

    def generate_api_key(self) -> str:
        """Generate API key for external integrations"""
        return secrets.token_urlsafe(32)

    def generate_unusable_password_hash(self) -> str:
        """A valid bcrypt hash of a random secret, for operator-created accounts.

        Such users authenticate via invite / magic link and can never log in with this
        password (it is random and never disclosed). Avoids guessable placeholder hashes.
        """
        return self.hash_password(secrets.token_urlsafe(32))


security_manager = SecurityManager()
