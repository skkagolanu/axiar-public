import json
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user, get_current_user_ws
from app.core.database import get_db_session
from app.core.websocket import manager
from app.domain.chat.models import ChatMessage
from app.domain.user.models import User

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket, current_user: User = Depends(get_current_user_ws), db: AsyncSession = Depends(get_db_session)
):
    """WebSocket endpoint for real-time chat with persistence"""
    if not current_user:
        return

    # Echo back the "access_token" subprotocol if the client offered it --
    # some strict clients/proxies expect the handshake response to name one of
    # the subprotocols the client requested.
    offered = [p.strip() for p in websocket.headers.get("sec-websocket-protocol", "").split(",")]
    subprotocol = "access_token" if "access_token" in offered else None

    await manager.connect(current_user.id, websocket, subprotocol=subprotocol)

    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)

            # zombie connection the browser's WS onclose never fired for (e.g. after
            # client suspension or a NAT timeout). Reply directly to the sender and skip the
            # persistence/broadcast logic below entirely -- a ping isn't a chat message.
            if message_data.get("type") == "ping":
                await websocket.send_json({"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()})
                continue

            # Save to database if booking_id provided
            if message_data.get("booking_id"):
                chat_msg = ChatMessage(
                    tenant_id=current_user.tenant_id,
                    booking_id=UUID(message_data["booking_id"]),
                    user_id=current_user.id,
                    message=message_data.get("content", ""),
                )
                db.add(chat_msg)
                await db.commit()

            message = {
                "type": message_data.get("type", "message"),
                "booking_id": message_data.get("booking_id"),
                "sender_id": str(current_user.id),
                "sender_name": f"{current_user.first_name} {current_user.last_name}",
                "content": message_data.get("content"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            if message_data.get("recipient_id"):
                recipient_id = UUID(message_data["recipient_id"])
                await manager.send_personal_message(message, recipient_id)
            elif message_data.get("booking_id"):
                await manager.send_personal_message(message, current_user.id)

    except WebSocketDisconnect:
        manager.disconnect(current_user.id, websocket)
    except Exception:
        manager.disconnect(current_user.id, websocket)


@router.get("/chat/{booking_id}/history", response_model=Dict[str, Any])
async def get_chat_history(
    booking_id: UUID,
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get chat history for a booking (tenant-scoped)"""
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.booking_id == booking_id, ChatMessage.tenant_id == current_user.tenant_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    )
    messages = list(reversed(result.scalars().all()))
    return {
        "booking_id": str(booking_id),
        "messages": [
            {
                "id": str(msg.id),
                "user_id": str(msg.user_id),
                "message": msg.message,
                "created_at": msg.created_at.isoformat(),
            }
            for msg in messages
        ],
    }
