import asyncio

import pytest

from app.core.security import security_manager


class TestSecurityManager:
    def test_password_hashing(self):
        """Test password hashing and verification"""
        password = "SecurePassword123!"
        hashed = security_manager.hash_password(password)

        assert security_manager.verify_password(password, hashed)
        assert not security_manager.verify_password("WrongPassword", hashed)

    def test_jwt_token_creation_and_verification(self):
        """Test JWT token creation and verification"""
        user_data = {"sub": "user123", "role": "provider"}
        token = security_manager.create_access_token(user_data)

        # Verify token
        payload = asyncio.run(security_manager.verify_token(token))
        assert payload["sub"] == "user123"
        assert payload["type"] == "access"

    def test_api_key_generation(self):
        """Test API key generation"""
        api_key = security_manager.generate_api_key()
        assert len(api_key) > 20
        assert isinstance(api_key, str)
