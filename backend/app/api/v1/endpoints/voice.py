from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.dependencies.auth import require_role
from app.domain.user.models import User, UserRole

router = APIRouter()


@router.post("/{booking_id}/voice-update", response_model=Dict[str, Any])
async def voice_update(
    booking_id: UUID,
    audio: UploadFile = File(...),
    current_user: User = Depends(require_role([UserRole.FIELD_AGENT])),
):
    """Process voice update for booking (speech-to-text)"""
    raise HTTPException(
        status_code=501,
        detail="Voice-to-text not implemented. Integrate a real STT provider (e.g. Whisper) and replace this endpoint.",
    )
