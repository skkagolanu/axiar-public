from typing import Optional
from uuid import UUID

import stripe

from app.core.config import settings
from app.core.exceptions import PaymentFailedError
from app.core.tenant_context import get_current_tenant, set_current_tenant
from app.domain.booking.repository import BookingRepository
from app.domain.payment.models import PaymentMethod, PaymentStatus
from app.domain.payment.repository import PaymentRepository

stripe.api_key = settings.STRIPE_SECRET_KEY
if settings.STRIPE_API_BASE:
    stripe.api_base = settings.STRIPE_API_BASE


class PaymentService:
    def __init__(self, payment_repo: PaymentRepository, booking_repo: BookingRepository):
        self.payment_repo = payment_repo
        self.booking_repo = booking_repo

    async def create_payment_intent(self, booking_id: UUID, amount_cents: int) -> dict:
        """Create Stripe payment intent"""
        # Hosted demo (DEMO_MODE): no Stripe account exists — record the payment
        # with a synthetic intent id and skip the network call. The client then
        # hits /payments/demo-confirm, which replays the same webhook success
        # path a real Stripe callback would.
        if settings.DEMO_MODE:
            from uuid import uuid4

            payment = await self.payment_repo.create(
                booking_id=booking_id,
                amount_cents=amount_cents,
                payment_method=PaymentMethod.CARD,
                stripe_payment_intent_id=f"demo_pi_{uuid4().hex}",
            )
            return {
                "payment_id": str(payment.id),
                "client_secret": "demo",
                "amount_cents": amount_cents,
            }

        try:
            
            # can restore tenant scope when it processes the callback.
            tenant_id = get_current_tenant()
            metadata = {"booking_id": str(booking_id)}
            if tenant_id:
                metadata["tenant_id"] = str(tenant_id)

            intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency="gbp",
                metadata=metadata,
            )

            payment = await self.payment_repo.create(
                booking_id=booking_id,
                amount_cents=amount_cents,
                payment_method=PaymentMethod.CARD,
                stripe_payment_intent_id=intent.id,
            )

            return {
                "payment_id": str(payment.id),
                "client_secret": intent.client_secret,
                "amount_cents": amount_cents,
            }

        except stripe.error.StripeError as e:
            raise PaymentFailedError(f"Failed to create payment intent: {str(e)}")

    async def handle_webhook_event(self, event: dict) -> None:
        """Handle Stripe webhook events"""
        event_type = event["type"]
        payment_intent = event["data"]["object"]

        
        # so the tenant-scoped payment/booking lookups below resolve correctly.
        metadata = payment_intent.get("metadata") or {}
        tenant_id = metadata.get("tenant_id")
        if tenant_id:
            try:
                set_current_tenant(UUID(tenant_id))
            except (ValueError, TypeError):
                pass

        payment = await self.payment_repo.get_by_stripe_intent(payment_intent["id"])
        if not payment:
            return

        if event_type == "payment_intent.succeeded":
            await self.payment_repo.update_status(
                payment.id,
                PaymentStatus.SUCCEEDED,
                stripe_charge_id=payment_intent.get("latest_charge"),
            )

            booking = await self.booking_repo.get_by_id(payment.booking_id)
            if booking:
                booking.total_paid_cents += payment.amount_cents

        elif event_type == "payment_intent.payment_failed":
            failure_message = payment_intent.get("last_payment_error", {}).get("message", "Unknown error")
            await self.payment_repo.update_status(payment.id, PaymentStatus.FAILED, failure_reason=failure_message)
