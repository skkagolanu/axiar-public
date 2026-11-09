from typing import Dict, List, Optional
from uuid import UUID

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db_session
from app.core.security import security_manager
from app.core.tenant_context import get_current_tenant, set_current_tenant
from app.domain.booking.repository import BookingRepository
from app.domain.payment.models import PaymentStatus
from app.domain.payment.repository import PaymentRepository
from app.domain.payment.schemas import PaymentCreate, PaymentResponse
from app.domain.payment.service import PaymentService
from app.domain.user.models import User

router = APIRouter()

# Non-raising bearer scheme so we can fall through to guest-token auth
_security_optional = HTTPBearer(auto_error=False)


@router.post("/create-intent", response_model=dict)
async def create_payment_intent(
    payment_data: PaymentCreate,
    db: AsyncSession = Depends(get_db_session),
    guest_token: Optional[str] = Header(None, alias="X-Guest-Token"),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_security_optional),
):
    """Create Stripe payment intent for a booking.

    Two authentication paths:

    1. **Authenticated user** — standard ``Authorization: Bearer <jwt>``.
       Booking must belong to ``current_user``.

    2. **Guest user** — ``X-Guest-Token`` header from the guest-booking response.
       The token is scoped to a single booking and expires after 30 minutes.
    """
    booking_repo = BookingRepository(db)
    await _authenticate_and_load_booking(booking_repo, payment_data.booking_id, db, guest_token, credentials)

    payment_repo = PaymentRepository(db)
    payment_service = PaymentService(payment_repo, booking_repo)

    result = await payment_service.create_payment_intent(
        booking_id=payment_data.booking_id, amount_cents=payment_data.amount_cents
    )

    await db.commit()
    return result


class DemoConfirmRequest(BaseModel):
    booking_id: UUID
    payment_id: UUID


@router.post("/demo-confirm", response_model=Dict[str, str])
async def demo_confirm_payment(
    body: DemoConfirmRequest,
    db: AsyncSession = Depends(get_db_session),
    guest_token: Optional[str] = Header(None, alias="X-Guest-Token"),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_security_optional),
):
    """Hosted-demo payment simulation (DEMO_MODE only — 404s otherwise).

    Auth is identical to ``create-intent`` (bearer user or booking-scoped guest
    token). Instead of Stripe confirming the card and calling our webhook, this
    replays the exact ``payment_intent.succeeded`` webhook path with a synthetic
    event, so the demo exercises the production success handling end-to-end.
    """
    if not settings.DEMO_MODE:
        raise HTTPException(status_code=404, detail="Not found")

    booking_repo = BookingRepository(db)
    booking = await _authenticate_and_load_booking(booking_repo, body.booking_id, db, guest_token, credentials)

    payment_repo = PaymentRepository(db)
    payment = await payment_repo.get_by_id(body.payment_id)
    if not payment or payment.booking_id != booking.id:
        raise HTTPException(status_code=404, detail="Payment not found for this booking")
    if payment.status == PaymentStatus.SUCCEEDED:
        return {"status": "succeeded"}  # idempotent — don't double-credit total_paid_cents

    tenant_id = get_current_tenant()
    event = {
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": payment.stripe_payment_intent_id,
                "metadata": {
                    "booking_id": str(booking.id),
                    **({"tenant_id": str(tenant_id)} if tenant_id else {}),
                },
                "latest_charge": "demo_charge",
            }
        },
    }
    payment_service = PaymentService(payment_repo, booking_repo)
    await payment_service.handle_webhook_event(event)
    await db.commit()
    return {"status": "succeeded"}


async def _authenticate_and_load_booking(
    booking_repo: BookingRepository,
    booking_id: UUID,
    db: AsyncSession,
    guest_token: Optional[str],
    credentials: Optional[HTTPAuthorizationCredentials],
):
    """Shared auth for payment endpoints: bearer user OR booking-scoped guest token.

    Authenticates first (so unauthenticated requests fail 401 before 404), loads
    the booking under the restored tenant scope, and enforces ownership for the
    bearer path. Returns the booking.
    """
    if credentials:
        # ── Authenticated user path ────────────────────────────────────────
        user = await _resolve_user_from_bearer(credentials, db)
    elif guest_token:
        # ── Guest token path ───────────────────────────────────────────────
        payload = await security_manager.verify_token(guest_token, expected_type="guest")
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid or expired guest token")

        token_booking_id = payload.get("booking_id")
        if not token_booking_id or str(booking_id) != token_booking_id:
            raise HTTPException(status_code=403, detail="Guest token does not match this booking")

        # Restore tenant scope for downstream tenant-scoped operations
        token_tenant_id = payload.get("tenant_id")
        if token_tenant_id:
            try:
                token_tenant_uuid = UUID(token_tenant_id)
            except ValueError:
                raise HTTPException(status_code=401, detail="Invalid tenant in guest token")
            request_tenant_id = get_current_tenant()
            if request_tenant_id and token_tenant_uuid != request_tenant_id:
                raise HTTPException(status_code=401, detail="Tenant mismatch")
            set_current_tenant(token_tenant_uuid)

        user = None
    else:
        raise HTTPException(
            status_code=401,
            detail="Authentication required — send Bearer token or X-Guest-Token header",
        )

    # Now load the booking with tenant scope set above
    booking = await booking_repo.get_by_id(booking_id)

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if user is not None and booking.customer_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    return booking


async def _resolve_user_from_bearer(
    credentials: HTTPAuthorizationCredentials,
    db: AsyncSession,
) -> User:
    """Replicate the Bearer-token → User resolution from ``get_current_user``
    so we can keep the dependency optional (auto_error=False) in the handler."""
    from sqlalchemy import select

    from app.core.tenant_context import get_current_tenant

    payload = await security_manager.verify_token(credentials.credentials, expected_type="access")
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    token_tenant_id = payload.get("tenant_id")
    request_tenant_id = get_current_tenant()

    if token_tenant_id:
        try:
            token_tenant_uuid = UUID(token_tenant_id)
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid tenant claim in token")
        if request_tenant_id and token_tenant_uuid != request_tenant_id:
            raise HTTPException(status_code=401, detail="Tenant mismatch")

    from app.domain.user.models import User

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    if token_tenant_id:
        token_tenant_uuid = UUID(token_tenant_id)
        if user.tenant_id != token_tenant_uuid:
            raise HTTPException(status_code=401, detail="Token tenant does not match user tenant")
        set_current_tenant(user.tenant_id)
    else:
        set_current_tenant(user.tenant_id)

    return user


@router.post("/webhook", status_code=status.HTTP_200_OK, response_model=Dict[str, str])
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db_session)):
    """Handle Stripe webhook events"""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    payment_repo = PaymentRepository(db)
    booking_repo = BookingRepository(db)
    payment_service = PaymentService(payment_repo, booking_repo)

    await payment_service.handle_webhook_event(event)
    await db.commit()

    return {"status": "success"}


@router.get("/booking/{booking_id}", response_model=List[PaymentResponse])
async def get_booking_payments(
    booking_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get all payments for a booking"""
    booking_repo = BookingRepository(db)
    booking = await booking_repo.get_by_id(booking_id)

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.customer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    payment_repo = PaymentRepository(db)
    payments = await payment_repo.get_by_booking(booking_id)

    return payments
