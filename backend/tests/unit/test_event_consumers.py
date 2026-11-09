"""Unit tests for domain event consumer handlers (X5)."""

from unittest.mock import AsyncMock, patch

import pytest

from app.consumers.booking_handlers import (
    BOOKING_HANDLERS,
    dispatch_booking_event,
    handle_booking_cancelled,
    handle_booking_completed,
    handle_booking_confirmed,
    handle_booking_created,
)
from app.consumers.payment_handlers import (
    PAYMENT_HANDLERS,
    dispatch_payment_event,
    handle_payment_completed,
    handle_payment_failed,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BOOKING_EVENT_BASE = {
    "event_id": "aaaaaaaa-0000-0000-0000-000000000001",
    "aggregate_id": "bbbbbbbb-0000-0000-0000-000000000002",
    "aggregate_type": "booking",
    "tenant_id": None,
    "occurred_at": "2026-06-30T10:00:00Z",
}


def _booking_event(event_type: str, **data_extra):
    return {
        **BOOKING_EVENT_BASE,
        "event_type": event_type,
        "data": {"customer_email": "alice@example.com", "customer_name": "Alice", **data_extra},
    }


# ---------------------------------------------------------------------------
# Booking handler tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_handle_booking_created_sends_email():
    event = _booking_event("booking.created")
    with patch("app.consumers.booking_handlers.notification_service") as mock_ns:
        mock_ns.send_email = AsyncMock()
        await handle_booking_created(event)
        mock_ns.send_email.assert_awaited_once()
        call_kwargs = mock_ns.send_email.call_args.kwargs
        assert call_kwargs["to_email"] == "alice@example.com"
        assert "received" in call_kwargs["subject"].lower()


@pytest.mark.unit
async def test_handle_booking_created_skips_when_no_email():
    event = _booking_event("booking.created")
    event["data"].pop("customer_email")
    with patch("app.consumers.booking_handlers.notification_service") as mock_ns:
        mock_ns.send_email = AsyncMock()
        await handle_booking_created(event)
        mock_ns.send_email.assert_not_awaited()


@pytest.mark.unit
async def test_handle_booking_confirmed_sends_email():
    event = _booking_event("booking.confirmed")
    with patch("app.consumers.booking_handlers.notification_service") as mock_ns:
        mock_ns.send_email = AsyncMock()
        await handle_booking_confirmed(event)
        mock_ns.send_email.assert_awaited_once()
        assert "confirmed" in mock_ns.send_email.call_args.kwargs["subject"].lower()


@pytest.mark.unit
async def test_handle_booking_completed_mentions_review():
    event = _booking_event("booking.completed")
    with patch("app.consumers.booking_handlers.notification_service") as mock_ns:
        mock_ns.send_email = AsyncMock()
        await handle_booking_completed(event)
        mock_ns.send_email.assert_awaited_once()
        body = mock_ns.send_email.call_args.kwargs["body"]
        assert "review" in body.lower()


@pytest.mark.unit
async def test_handle_booking_cancelled_sends_email():
    event = _booking_event("booking.cancelled")
    with patch("app.consumers.booking_handlers.notification_service") as mock_ns:
        mock_ns.send_email = AsyncMock()
        await handle_booking_cancelled(event)
        mock_ns.send_email.assert_awaited_once()
        assert "cancelled" in mock_ns.send_email.call_args.kwargs["subject"].lower()


@pytest.mark.unit
async def test_dispatch_booking_event_routes_correctly():
    """dispatch_booking_event calls the right handler for each event_type."""
    for event_type in BOOKING_HANDLERS:
        event = _booking_event(event_type)
        fake_handler = AsyncMock()
        with patch.dict(
            "app.consumers.booking_handlers.BOOKING_HANDLERS",
            {event_type: fake_handler},
        ):
            await dispatch_booking_event(event)
            fake_handler.assert_awaited_once_with(event)


@pytest.mark.unit
async def test_dispatch_booking_event_ignores_unknown_type():
    event = {**BOOKING_EVENT_BASE, "event_type": "booking.unknown", "data": {}}
    # Should not raise; simply returns None
    await dispatch_booking_event(event)


# ---------------------------------------------------------------------------
# Payment handler tests
# ---------------------------------------------------------------------------


def _payment_event(event_type: str, **data_extra):
    return {
        "event_id": "cccccccc-0000-0000-0000-000000000001",
        "aggregate_id": "dddddddd-0000-0000-0000-000000000002",
        "aggregate_type": "payment",
        "event_type": event_type,
        "tenant_id": None,
        "occurred_at": "2026-06-30T10:00:00Z",
        "data": {
            "customer_email": "bob@example.com",
            "customer_name": "Bob",
            "amount_cents": 5000,
            "booking_id": "eeeeeeee-0000-0000-0000-000000000003",
            **data_extra,
        },
    }


@pytest.mark.unit
async def test_handle_payment_completed_includes_amount():
    event = _payment_event("payment.completed")
    with patch("app.consumers.payment_handlers.notification_service") as mock_ns:
        mock_ns.send_email = AsyncMock()
        await handle_payment_completed(event)
        mock_ns.send_email.assert_awaited_once()
        body = mock_ns.send_email.call_args.kwargs["body"]
        assert "£50.00" in body


@pytest.mark.unit
async def test_handle_payment_failed_sends_action_required():
    event = _payment_event("payment.failed")
    with patch("app.consumers.payment_handlers.notification_service") as mock_ns:
        mock_ns.send_email = AsyncMock()
        await handle_payment_failed(event)
        mock_ns.send_email.assert_awaited_once()
        assert "action required" in mock_ns.send_email.call_args.kwargs["subject"].lower()


@pytest.mark.unit
async def test_handle_payment_completed_skips_when_no_email():
    event = _payment_event("payment.completed")
    event["data"].pop("customer_email")
    with patch("app.consumers.payment_handlers.notification_service") as mock_ns:
        mock_ns.send_email = AsyncMock()
        await handle_payment_completed(event)
        mock_ns.send_email.assert_not_awaited()


@pytest.mark.unit
async def test_dispatch_payment_event_ignores_unknown_type():
    event = _payment_event("payment.refunded")
    # No handler registered for refunded — should not raise
    await dispatch_payment_event(event)
