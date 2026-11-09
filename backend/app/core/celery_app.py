from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "axiar",
    broker=getattr(settings, "REDIS_URL", "redis://localhost:6379/0"),
    backend=getattr(settings, "REDIS_URL", "redis://localhost:6379/0"),
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,
    worker_prefetch_multiplier=4,
)

celery_app.conf.beat_schedule = {
    "send-booking-reminders": {
        "task": "app.tasks.notifications.send_booking_reminders",
        "schedule": crontab(hour="*/1"),
    },
    "detect-overdue-bookings": {
        "task": "app.tasks.notifications.detect_overdue_bookings",
        "schedule": crontab(minute="*/5"),
    },
}
