import logging

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client

from app.core.config import settings
from app.core.demo_integrations import demo_integrations

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self):
        self.sendgrid = None
        self.twilio = None

        if settings.DEMO_MODE:
            return

        try:
            if settings.SENDGRID_API_KEY and not settings.SENDGRID_API_KEY.startswith("mock"):
                self.sendgrid = SendGridAPIClient(api_key=settings.SENDGRID_API_KEY)
        except Exception as e:
            logger.warning(f"SendGrid not configured: {e}")

        try:
            if settings.TWILIO_ACCOUNT_SID and not settings.TWILIO_ACCOUNT_SID.startswith("mock"):
                self.twilio = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        except Exception as e:
            logger.warning(f"Twilio not configured: {e}")

    async def send_booking_confirmation(self, booking_data: dict):
        """Send booking confirmation email"""
        if settings.DEMO_MODE:
            return demo_integrations.notification_result("email", booking_data["customer_email"])
        if not self.sendgrid:
            logger.info(f"Mock: Booking confirmation email to {booking_data['customer_email']}")
            return {"status": "mock", "message": "SendGrid not configured"}

        try:
            message = Mail(
                from_email="contact@example.test",
                to_emails=booking_data["customer_email"],
                subject="Booking Confirmed",
                html_content=f"""
                <h2>Booking Confirmed</h2>
                <p>Your booking for {booking_data['service_name']} has been confirmed.</p>
                <p>Date: {booking_data['scheduled_time']}</p>
                <p>Location: {booking_data['location_address']}</p>
                """,
            )
            response = self.sendgrid.send(message)
            return {"status": "sent", "code": response.status_code}
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return {"status": "error", "message": str(e)}

    async def send_sms_reminder(self, phone: str, message: str):
        """Send SMS reminder"""
        if settings.DEMO_MODE:
            return demo_integrations.notification_result("sms", phone)
        if not self.twilio:
            logger.info(f"Mock: SMS to {phone}: {message}")
            return {"status": "mock", "message": "Twilio not configured"}

        try:
            msg = self.twilio.messages.create(body=message, from_=settings.TWILIO_PHONE_NUMBER, to=phone)
            return {"status": "sent", "sid": msg.sid}
        except Exception as e:
            logger.error(f"SMS send failed: {e}")
            return {"status": "error", "message": str(e)}

    async def send_booking_reminder(self, booking_data: dict):
        """Send booking reminder 24h before"""
        message = f"Reminder: Your {booking_data['service_name']} appointment is tomorrow at {booking_data['scheduled_time']}"
        return await self.send_sms_reminder(booking_data["customer_phone"], message)

    async def send_email(self, to_email: str, subject: str, body: str):
        """Send a generic (HTML) email."""
        if settings.DEMO_MODE:
            return demo_integrations.notification_result("email", to_email)
        if not self.sendgrid:
            logger.info(f"Mock: email to {to_email} | {subject}")
            return {"status": "mock", "message": "SendGrid not configured"}

        try:
            message = Mail(
                from_email=settings.SENDGRID_FROM_EMAIL,
                to_emails=to_email,
                subject=subject,
                html_content=body,
            )
            response = self.sendgrid.send(message)
            return {"status": "sent", "code": response.status_code}
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return {"status": "error", "message": str(e)}


notification_service = NotificationService()
