from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_context import get_current_tenant
from app.domain.payment.schedule import PaymentSchedule, PaymentScheduleStatus


class PaymentScheduleRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _apply_tenant_filter(self, query):
        """Apply tenant filter to query"""
        tenant_id = get_current_tenant()
        if tenant_id:
            return query.where(PaymentSchedule.tenant_id == tenant_id)
        return query

    async def create_schedule(self, booking_id: UUID, milestones: List[dict]) -> List[PaymentSchedule]:
        """Create payment schedule with milestones"""
        from datetime import datetime

        tenant_id = get_current_tenant()
        if not tenant_id:
            raise ValueError("Tenant context required")

        schedules = []
        for milestone in milestones:
            due_date = milestone["due_date"]
            if isinstance(due_date, str):
                due_date = datetime.fromisoformat(due_date.replace("Z", "+00:00"))

            schedule = PaymentSchedule(
                tenant_id=tenant_id,
                booking_id=booking_id,
                milestone_name=milestone["milestone_name"],
                amount_cents=milestone["amount_cents"],
                due_date=due_date,
            )
            self.session.add(schedule)
            schedules.append(schedule)

        await self.session.flush()
        return schedules

    async def get_by_booking(self, booking_id: UUID) -> List[PaymentSchedule]:
        """Get all payment schedules for a booking"""
        query = select(PaymentSchedule).where(PaymentSchedule.booking_id == booking_id).order_by(PaymentSchedule.due_date)
        query = self._apply_tenant_filter(query)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def mark_paid(self, schedule_id: UUID, payment_id: UUID) -> Optional[PaymentSchedule]:
        """Mark schedule as paid"""
        query = select(PaymentSchedule).where(PaymentSchedule.id == schedule_id)
        query = self._apply_tenant_filter(query)
        result = await self.session.execute(query)
        schedule = result.scalar_one_or_none()

        if schedule:
            schedule.status = PaymentScheduleStatus.PAID
            schedule.payment_id = payment_id
            schedule.paid_at = datetime.now(timezone.utc)
            await self.session.flush()

        return schedule

    async def get_overdue(self) -> List[PaymentSchedule]:
        """Get overdue payment schedules"""
        now = datetime.now(timezone.utc)
        query = (
            select(PaymentSchedule)
            .where(
                PaymentSchedule.status == PaymentScheduleStatus.PENDING,
                PaymentSchedule.due_date < now,
            )
            .order_by(PaymentSchedule.due_date)
        )
        query = self._apply_tenant_filter(query)
        result = await self.session.execute(query)
        return list(result.scalars().all())
