"""Chat repository for data access layer"""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.chat.models import ChatMessage


class ChatRepository:
    """Repository for chat data access"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_booking(self, booking_id: UUID) -> List[ChatMessage]:
        """Get all chat messages for a booking"""
        query = select(ChatMessage).where(ChatMessage.booking_id == booking_id).order_by(ChatMessage.created_at)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create(self, message: ChatMessage) -> ChatMessage:
        """Create new chat message"""
        self.session.add(message)
        await self.session.flush()
        await self.session.refresh(message)
        return message
