"""User repository for data access layer"""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_context import get_current_tenant
from app.domain.user.models import User, UserRole


class UserRepository:
    """Repository for user data access"""

    def __init__(self, session: AsyncSession):
        self.session = session

    def _apply_tenant_filter(self, query):
        """Scope the query to the current request tenant when one is resolved."""
        current_tenant_id = get_current_tenant()
        if current_tenant_id:
            return query.where(User.tenant_id == current_tenant_id)
        return query

    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        """Get user by ID within the current tenant."""
        query = self._apply_tenant_filter(select(User).where(User.id == user_id))
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email across tenants (required for login)."""
        query = select(User).where(User.email == email)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_all(self, skip: int = 0, limit: int = 100, role: Optional[UserRole] = None) -> List[User]:
        """Get all users within the current tenant with pagination."""
        query = self._apply_tenant_filter(select(User).offset(skip).limit(limit))
        if role:
            query = query.where(User.role == role)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create(self, user: User) -> User:
        """Create new user"""
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def update(self, user: User) -> User:
        """Update user"""
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def delete(self, user_id: UUID) -> bool:
        """Delete user"""
        user = await self.get_by_id(user_id)
        if user:
            await self.session.delete(user)
            await self.session.flush()
            return True
        return False
