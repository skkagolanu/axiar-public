import secrets
from typing import List
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user, require_role
from app.core.cache import cache_manager as cache
from app.core.config import settings
from app.core.database import get_db_session
from app.core.security import security_manager
from app.domain.booking.models import BookingStatus, FieldAgent, Provider, Service
from app.domain.booking.repository import BookingRepository
from app.domain.booking.schemas import BookingCreate
from app.domain.booking.schemas import BookingRead as BookingResponse
from app.domain.booking.schemas import BookingReadEnriched, BookingUpdate, GuestBookingCreate
from app.domain.promo.repository import PromoCodeRepository
from app.domain.provider.repository import ProviderRepository
from app.domain.user.models import User, UserRole
from app.services.notification_service import notification_service

router = APIRouter()


async def _caller_provider_id(db: AsyncSession, current_user: User) -> UUID | None:
    """Resolve the caller's Provider.id independently of their User.id."""
    return await ProviderRepository(db).get_id_by_user_id(current_user.id)


async def _caller_field_agent_id(db: AsyncSession, current_user: User) -> UUID | None:
    """The caller's own ``FieldAgent.id`` (also its own PK, not a ``User.id``)."""
    agent = (
        await db.execute(
            select(FieldAgent).where(
                FieldAgent.user_id == current_user.id,
                FieldAgent.tenant_id == current_user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    return agent.id if agent else None


async def _visibility_filter(db: AsyncSession, current_user: User) -> dict | None:
    """Repository filter kwargs restricting a booking listing to this caller's own rows.

    Returns ``None`` when the caller can see nothing (e.g. a provider with no profile).
    Admins get ``{}`` — the whole tenant.
    """
    if current_user.role == UserRole.ADMIN:
        return {}
    if current_user.role == UserRole.PROVIDER:
        provider_id = await _caller_provider_id(db, current_user)
        return {"provider_id": provider_id} if provider_id else None
    if current_user.role == UserRole.FIELD_AGENT:
        agent_id = await _caller_field_agent_id(db, current_user)
        return {"field_agent_id": agent_id} if agent_id else None
    return {"customer_id": current_user.id}


async def _can_access_booking(db: AsyncSession, booking, current_user: User) -> bool:
    """Object-level authorization for a single booking."""
    if current_user.role == UserRole.ADMIN:
        return True
    if booking.customer_id == current_user.id:
        return True
    if current_user.role == UserRole.PROVIDER:
        return booking.provider_id == await _caller_provider_id(db, current_user)
    if current_user.role == UserRole.FIELD_AGENT:
        return booking.field_agent_id is not None and booking.field_agent_id == await _caller_field_agent_id(db, current_user)
    return False


class GuestBookingResponse(BookingResponse):
    """Booking response for unauthenticated guests — includes a short-lived JWT for subsequent
    payment-intent calls (``X-Guest-Token`` header)."""

    guest_token: str = Field(default="", description="Short-lived JWT for guest payment flow")


@router.post("/guest", response_model=GuestBookingResponse, status_code=status.HTTP_201_CREATED)
async def create_guest_booking(
    payload: GuestBookingCreate,
    db: AsyncSession = Depends(get_db_session),
):
    """Create a booking without an account.

    Finds or creates a customer User from the supplied email/name/phone, creates the
    booking, then sends a magic link so the guest can later track or manage it.
    """
    from app.domain.tenant.models import Tenant

    tenant_result = await db.execute(select(Tenant).where(Tenant.slug == "default"))
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=500, detail="Default tenant not found")

    # Find-or-create the guest user (no password — magic-link auth only)
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            id=uuid4(),
            tenant_id=tenant.id,
            email=payload.email,
            first_name=payload.first_name,
            last_name=payload.last_name,
            phone=payload.phone,
            role=UserRole.CUSTOMER,
            is_active=True,
            is_verified=False,
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)

    bd = payload.booking_data
    # Validate referenced entities
    provider = (await db.execute(select(Provider).where(Provider.id == bd.provider_id))).scalar_one_or_none()
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    service = (await db.execute(select(Service).where(Service.id == bd.service_id))).scalar_one_or_none()
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")

    repo = BookingRepository(db)
    booking = await repo.create(
        customer_id=user.id,
        provider_id=bd.provider_id,
        service_id=bd.service_id,
        scheduled_time=bd.scheduled_time,
        duration_minutes=bd.duration_minutes,
        location_postcode=bd.location_postcode,
        base_price_cents=bd.base_price_cents,
        description=bd.description,
        location_address=bd.location_address,
        payment_timing=bd.payment_timing,
        deposit_percentage=bd.deposit_percentage,
    )
    await db.commit()

    # Generate a short-lived guest token so the frontend can call the payment-intent
    # endpoint without a regular user JWT.  The sub is prefixed with "guest:" to
    # distinguish it from regular user tokens.
    from datetime import timedelta

    guest_token = security_manager.create_access_token(
        data={"sub": f"guest:{booking.id}"},
        expires_delta=timedelta(minutes=30),
        extra_claims={
            "type": "guest",
            "booking_id": str(booking.id),
            "tenant_id": str(booking.tenant_id),
            "email": payload.email,
        },
    )

    # Send magic link so the guest can view/manage their booking
    magic_token = secrets.token_urlsafe(32)
    await cache.set(f"magic_link:{magic_token}", payload.email, ttl=86400)  # 24 h
    confirm_url = f"{settings.FRONTEND_URL}/book/confirm?token={magic_token}&booking={booking.id}"
    await notification_service.send_email(
        to_email=payload.email,
        subject="Your booking confirmation — view or manage it here",
        body=(
            f"<p>Hi {payload.first_name},</p>"
            f"<p>Your booking has been received. "
            f'<a href="{confirm_url}">Click here to view or manage it</a>. '
            f"This link expires in 24 hours.</p>"
        ),
    )

    return {**BookingResponse.model_validate(booking).model_dump(), "guest_token": guest_token}


@router.get("/", response_model=List[BookingReadEnriched])
async def list_bookings(
    skip: int = Query(0, ge=0, le=1_000_000),
    limit: int = Query(100, ge=1, le=500),
    status: BookingStatus | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """List bookings the caller is entitled to see, display-enriched in one query.

    Scoped by role — customers see their own, providers their provider's, field agents
    the ones assigned to them, admins the whole tenant. The tenant filter alone is not an
    authorization boundary: every customer in a tenant shares it, and the enriched rows
    carry other customers' names and addresses.

    Projects the same public fields in one scoped query, without hydrating unrelated
    ORM entity graphs or issuing N+1 follow-up fetches.
    """
    scope = await _visibility_filter(db, current_user)
    if scope is None:
        return []

    repo = BookingRepository(db)
    bookings = await repo.list_enriched(skip=skip, limit=limit, status=status, **scope)
    return [BookingReadEnriched.model_validate(b) for b in bookings]


@router.post("/", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
async def create_booking(
    booking_data: BookingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Create a new booking"""
    repo = BookingRepository(db)
    promo_repo = PromoCodeRepository(db)

    # Apply promo code if provided
    discount_cents = 0
    if booking_data.promo_code:
        valid, discount_cents, message = await promo_repo.validate_and_apply(
            booking_data.promo_code, booking_data.base_price_cents
        )
        if not valid:
            raise HTTPException(status_code=400, detail=message)

    # The repository validates both references under the tenant-scoped provider
    # lock; repeating those lookups here adds round trips without stronger checks.
    booking = await repo.create(
        customer_id=current_user.id,
        provider_id=booking_data.provider_id,
        service_id=booking_data.service_id,
        scheduled_time=booking_data.scheduled_time,
        duration_minutes=booking_data.duration_minutes,
        location_postcode=booking_data.location_postcode,
        base_price_cents=booking_data.base_price_cents,
        description=booking_data.description,
        location_address=booking_data.location_address,
        payment_timing=booking_data.payment_timing,
        deposit_percentage=booking_data.deposit_percentage,
    )

    # Apply promo code discount
    if discount_cents > 0:
        booking.promo_code = booking_data.promo_code.upper()
        booking.discount_cents = discount_cents
        await promo_repo.increment_usage(booking_data.promo_code)

    # Calculate deposit for split payments
    final_price = booking.base_price_cents - discount_cents
    if booking.payment_timing == "split_payment":
        booking.deposit_paid_cents = int(final_price * booking.deposit_percentage / 100)

    await db.commit()
    return booking


@router.get("/my-bookings", response_model=List[BookingResponse])
async def get_my_bookings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get current user's bookings"""
    repo = BookingRepository(db)
    bookings = await repo.get_by_customer(current_user.id)
    return bookings


@router.get("/{booking_id}", response_model=BookingResponse)
async def get_booking(
    booking_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get booking by ID"""
    repo = BookingRepository(db)
    booking = await repo.get_by_id(booking_id, with_relationships=False)

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if not await _can_access_booking(db, booking, current_user):
        raise HTTPException(status_code=403, detail="Access denied")

    return booking


@router.patch("/{booking_id}/status", response_model=BookingResponse)
async def update_booking_status(
    booking_id: UUID,
    update_data: BookingUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Update booking status"""
    repo = BookingRepository(db)
    booking = await repo.get_by_id(booking_id, with_relationships=False)

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Customers may cancel their own bookings. Providers may update bookings
    # owned by their provider profile; admins may update any booking in the tenant.
    is_customer_cancelling = booking.customer_id == current_user.id and update_data.status == BookingStatus.CANCELLED
    is_admin = current_user.role == UserRole.ADMIN
    is_owning_provider = current_user.role == UserRole.PROVIDER and booking.provider_id == await _caller_provider_id(
        db, current_user
    )

    if not (is_customer_cancelling or is_owning_provider or is_admin):
        raise HTTPException(status_code=403, detail="Not authorized to update this booking status")

    updated_booking = await repo.update_status(booking_id, update_data.status, loaded_booking=booking)

    # Completion accounting for after-service payment terms.
    if update_data.status == BookingStatus.COMPLETED and booking.payment_timing == "after_service":
        if booking.total_paid_cents < booking.base_price_cents:
            booking.total_paid_cents = booking.base_price_cents

    # Completion accounting for split-payment terms.
    if update_data.status == BookingStatus.COMPLETED and booking.payment_timing == "split_payment":
        remaining = booking.base_price_cents - booking.deposit_paid_cents
        if booking.total_paid_cents < booking.base_price_cents:
            booking.total_paid_cents = booking.base_price_cents

    await db.commit()

    return updated_booking


@router.post("/{booking_id}/delay", response_model=BookingResponse)
async def report_delay(
    booking_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Field agent or provider reports they are running late on an active booking.
    Transitions the booking to DELAYED status (valid from ON_MY_WAY or ARRIVED).
    """
    repo = BookingRepository(db)
    booking = await repo.get_by_id(booking_id, with_relationships=False)

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Authorize ownership through FieldAgent.id and Provider.id, resolved
    # from the caller's user account.
    is_assigned_agent = (
        current_user.role == UserRole.FIELD_AGENT
        and booking.field_agent_id is not None
        and booking.field_agent_id == await _caller_field_agent_id(db, current_user)
    )
    is_owning_provider = current_user.role == UserRole.PROVIDER and booking.provider_id == await _caller_provider_id(
        db, current_user
    )
    is_admin = current_user.role == UserRole.ADMIN
    if not (is_assigned_agent or is_owning_provider or is_admin):
        raise HTTPException(status_code=403, detail="Only the assigned agent or the owning provider/admin can report a delay")

    updated = await repo.update_status(booking_id, BookingStatus.DELAYED, loaded_booking=booking)
    await db.commit()
    return updated


@router.get("/provider/{provider_id}", response_model=List[BookingResponse])
async def get_provider_bookings(
    provider_id: UUID,
    current_user: User = Depends(require_role([UserRole.PROVIDER, UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db_session),
):
    """Get bookings for a provider"""
    # provider_id is a Provider.id, not a User.id — resolve the caller's provider profile.
    if current_user.role == UserRole.PROVIDER:
        provider = await ProviderRepository(db).get_by_user_id(current_user.id)
        if not provider or provider.id != provider_id:
            raise HTTPException(status_code=403, detail="Access denied")

    repo = BookingRepository(db)
    bookings = await repo.get_by_provider(provider_id)
    return bookings
