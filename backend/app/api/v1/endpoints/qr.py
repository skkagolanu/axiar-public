from io import BytesIO
from uuid import UUID

import qrcode
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user
from app.core.database import get_db_session
from app.domain.booking.repository import BookingRepository
from app.domain.user.models import User

router = APIRouter()


@router.get("/{booking_id}/qr", response_class=StreamingResponse)
async def generate_booking_qr(
    booking_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Generate QR code for booking"""
    booking_repo = BookingRepository(db)
    booking = await booking_repo.get_by_id(booking_id)

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.customer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    qr_data = f"axiar://booking/{booking_id}"
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(qr_data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return StreamingResponse(buf, media_type="image/png")
