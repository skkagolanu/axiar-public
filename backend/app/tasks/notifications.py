import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.celery_app import celery_app
from app.core.config import settings
from app.domain.booking.models import Booking, BookingStatus
from app.services.notification_service import notification_service


def _run(coro):
    """Run an async coroutine to completion from inside a synchronous Celery task.

    Celery's default (prefork) worker has no running event loop, so each task gets a
    fresh one via asyncio.run.
    """
    return asyncio.run(coro)


@asynccontextmanager
async def _task_session():
    """Short-lived DB session bound to the current event loop.

    Each Celery task runs in its own event loop (see _run), so we must NOT reuse the
    app-wide async engine — its pooled connections are bound to the app's loop and would
    raise cross-loop errors. We build a throwaway NullPool engine per task and dispose it.
    """
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    try:
        session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_maker() as session:
            yield session
    finally:
        await engine.dispose()


async def _send_booking_confirmation(booking_id: str, email: str | None = None):
    async with _task_session() as session:
        result = await session.execute(select(Booking).where(Booking.id == booking_id))
        booking = result.scalar_one_or_none()
        if not booking:
            return {"status": "error", "message": "Booking not found"}

        # Relationships are lazy="joined" on Booking, so they load with the row.
        payload = {
            "customer_email": email or (booking.customer.email if booking.customer else None),
            "service_name": booking.service.name if booking.service else "your service",
            "scheduled_time": booking.scheduled_time.isoformat(),
            "location_address": booking.location_address or booking.location_postcode,
        }

    if not payload["customer_email"]:
        return {"status": "error", "message": "No customer email"}
    return await notification_service.send_booking_confirmation(payload)


async def _send_booking_reminder(booking_id: str, phone: str):
    async with _task_session() as session:
        result = await session.execute(select(Booking).where(Booking.id == booking_id))
        booking = result.scalar_one_or_none()
        if not booking:
            return {"status": "error", "message": "Booking not found"}

        service_name = booking.service.name if booking.service else "your appointment"
        scheduled_time = booking.scheduled_time.isoformat()
        message = f"Reminder: Your {service_name} appointment is tomorrow at {scheduled_time}."

    return await notification_service.send_sms_reminder(phone, message)


async def _send_booking_reminders():
    async with _task_session() as session:
        now = datetime.now(timezone.utc)
        tomorrow = now + timedelta(days=1)
        tomorrow_start = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_end = tomorrow.replace(hour=23, minute=59, second=59, microsecond=0)

        result = await session.execute(
            select(Booking).where(
                and_(
                    Booking.scheduled_time >= tomorrow_start,
                    Booking.scheduled_time <= tomorrow_end,
                    Booking.status == BookingStatus.CONFIRMED,
                )
            )
        )
        bookings = result.scalars().all()

        # DB connection while dispatching to the broker.
        targets = [
            (str(booking.id), booking.customer.phone) for booking in bookings if booking.customer and booking.customer.phone
        ]

    for booking_id, phone in targets:
        send_sms_reminder.delay(booking_id, phone)

    return {"reminders_sent": len(targets)}


@celery_app.task(bind=True, max_retries=3)
def send_booking_confirmation(self, booking_id: str, email: str | None = None):
    """Send booking confirmation email."""
    try:
        return _run(_send_booking_confirmation(booking_id, email))
    except Exception as exc:
        raise self.retry(countdown=60 * (2**self.request.retries), exc=exc)


@celery_app.task(bind=True, max_retries=3)
def send_sms_reminder(self, booking_id: str, phone: str):
    """Send an SMS reminder for an upcoming booking."""
    try:
        return _run(_send_booking_reminder(booking_id, phone))
    except Exception as exc:
        raise self.retry(countdown=60 * (2**self.request.retries), exc=exc)


@celery_app.task
def send_booking_reminders():
    """Beat task: enqueue SMS reminders for tomorrow's confirmed bookings."""
    return _run(_send_booking_reminders())


async def _detect_overdue_bookings():
    from app.domain.booking.models import BOOKING_STATUS_TRANSITIONS

    async with _task_session() as session:
        now = datetime.now(timezone.utc)
        overdue_cutoff = now - timedelta(minutes=15)

        result = await session.execute(
            select(Booking).where(
                Booking.status.in_([BookingStatus.ASSIGNED, BookingStatus.ON_MY_WAY]),
                Booking.scheduled_time <= overdue_cutoff,
            )
        )
        bookings = result.scalars().all()

        targets = []
        for booking in bookings:
            current_status = BookingStatus(booking.status)
            allowed = BOOKING_STATUS_TRANSITIONS.get(current_status, set())
            if BookingStatus.DELAYED in allowed:
                booking.status = BookingStatus.DELAYED
                if booking.customer and booking.customer.phone:
                    targets.append((str(booking.id), booking.customer.phone))

        if bookings:
            await session.commit()

    for booking_id, phone in targets:
        notify_late_booking.delay(booking_id, phone)

    return {"overdue_detected": len(bookings), "notifications_queued": len(targets)}


async def _notify_late_booking(booking_id: str, phone: str):
    async with _task_session() as session:
        result = await session.execute(select(Booking).where(Booking.id == booking_id))
        booking = result.scalar_one_or_none()
        if not booking:
            return {"status": "error", "message": "Booking not found"}

        service_name = booking.service.name if booking.service else "your booking"
        message = f"We're running late for your {service_name} appointment. We apologize for the delay."

    return await notification_service.send_sms_reminder(phone, message)


@celery_app.task(bind=True, max_retries=3)
def notify_late_booking(self, booking_id: str, phone: str):
    """Notify customer that their booking is running late."""
    try:
        return _run(_notify_late_booking(booking_id, phone))
    except Exception as exc:
        raise self.retry(countdown=60, exc=exc)


@celery_app.task
def detect_overdue_bookings():
    """Beat task: detect and flag overdue bookings every 5 minutes."""
    return _run(_detect_overdue_bookings())
