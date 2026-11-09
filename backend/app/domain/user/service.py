"""User service for business logic"""

from typing import Optional
from uuid import UUID

from app.core.security import security_manager
from app.domain.user.models import User
from app.domain.user.repository import UserRepository


class UserService:
    """Service for user business logic"""

    def __init__(self, repository: UserRepository):
        self.repository = repository

    async def authenticate(self, email: str, password: str) -> Optional[User]:
        """Authenticate user with email and password"""
        user = await self.repository.get_by_email(email)
        if not user or not user.hashed_password:
            return None

        if not security_manager.verify_password(password, user.hashed_password):
            return None

        if not user.is_active:
            return None

        return user

    async def update_status(self, user_id: UUID, is_active: bool) -> Optional[User]:
        """Update user active status"""
        user = await self.repository.get_by_id(user_id)
        if not user:
            return None

        user.is_active = is_active
        return await self.repository.update(user)
