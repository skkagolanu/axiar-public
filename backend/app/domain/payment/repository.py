from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_bus import event_bus
from app.core.events import PaymentCompleted, PaymentCreated, PaymentFailed
from app.core.tenant_context import get_current_tenant
from app.domain.payment.models import Payment, PaymentMethod, PaymentStatus


class PaymentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _apply_tenant_filter(self, query):
        """Apply tenant filter to query"""
        tenant_id = get_current_tenant()
        if tenant_id:
            return query.where(Payment.tenant_id == tenant_id)
        return query

    async def create(
        self,
        booking_id: UUID,
        amount_cents: int,
        payment_method: PaymentMethod,
        stripe_payment_intent_id: Optional[str] = None,
    ) -> Payment:
        """Create a new payment record"""
        tenant_id = get_current_tenant()
        if not tenant_id:
            raise ValueError("Tenant context required")

        payment = Payment(
            tenant_id=tenant_id,
            booking_id=booking_id,
            amount_cents=amount_cents,
            method=payment_method,
            status=PaymentStatus.PENDING,
            stripe_payment_intent_id=stripe_payment_intent_id,
        )

        self.session.add(payment)
        await self.session.flush()
        await self.session.refresh(payment)

        # Publish event
        await event_bus.publish(
            PaymentCreated(
                aggregate_id=payment.id,
                tenant_id=tenant_id,
                data={
                    "booking_id": str(booking_id),
                    "amount_cents": amount_cents,
                    "payment_method": payment_method.value,
                },
            )
        )

        return payment

    async def get_by_id(self, payment_id: UUID) -> Optional[Payment]:
        """Get payment by ID"""
        query = select(Payment).where(Payment.id == payment_id)
        query = self._apply_tenant_filter(query)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_stripe_intent(self, stripe_payment_intent_id: str) -> Optional[Payment]:
        """Get payment by Stripe payment intent ID"""
        query = select(Payment).where(Payment.stripe_payment_intent_id == stripe_payment_intent_id)
        query = self._apply_tenant_filter(query)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_booking(self, booking_id: UUID) -> List[Payment]:
        """Get all payments for a booking"""
        query = select(Payment).where(Payment.booking_id == booking_id).order_by(Payment.created_at.desc())
        query = self._apply_tenant_filter(query)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_status(
        self,
        payment_id: UUID,
        new_status: PaymentStatus,
        stripe_charge_id: Optional[str] = None,
        failure_reason: Optional[str] = None,
    ) -> Optional[Payment]:
        """Update payment status"""
        payment = await self.get_by_id(payment_id)
        if not payment:
            return None

        payment.status = new_status

        if new_status == PaymentStatus.SUCCEEDED:
            payment.paid_at = datetime.now(timezone.utc)
            if stripe_charge_id:
                payment.stripe_charge_id = stripe_charge_id

        if new_status == PaymentStatus.FAILED and failure_reason:
            payment.failure_reason = failure_reason

        await self.session.flush()
        await self.session.refresh(payment)

        # Publish status change events
        if new_status == PaymentStatus.SUCCEEDED:
            await event_bus.publish(
                PaymentCompleted(
                    aggregate_id=payment.id,
                    tenant_id=payment.tenant_id,
                    data={"booking_id": str(payment.booking_id), "amount_cents": payment.amount_cents},
                )
            )
        elif new_status == PaymentStatus.FAILED:
            await event_bus.publish(
                PaymentFailed(
                    aggregate_id=payment.id,
                    tenant_id=payment.tenant_id,
                    data={"booking_id": str(payment.booking_id), "failure_reason": failure_reason},
                )
            )

        return payment
