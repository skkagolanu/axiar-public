"""Chat service for business logic"""

from typing import Any, Dict, List
from uuid import UUID

from app.domain.chat.models import ChatMessage
from app.domain.chat.repository import ChatRepository


class ChatService:
    """Service for chat business logic"""

    def __init__(self, repository: ChatRepository):
        self.repository = repository

    async def get_history(self, booking_id: UUID) -> Dict[str, Any]:
        """Get chat history for a booking"""
        messages = await self.repository.get_by_booking(booking_id)
        return {
            "messages": [
                {
                    "id": str(msg.id),
                    "sender_id": str(msg.sender_id),
                    "message": msg.message,
                    "created_at": msg.created_at.isoformat(),
                }
                for msg in messages
            ]
        }

    async def send_message(self, booking_id: UUID, sender_id: UUID, message: str) -> ChatMessage:
        """Send a chat message"""
        chat_message = ChatMessage(booking_id=booking_id, sender_id=sender_id, message=message)
        return await self.repository.create(chat_message)
