"""Unit tests for BookingReadEnriched.from_booking (no DB; duck-typed ORM object)."""

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.domain.booking.schemas import BookingReadEnriched, BookingStatus, PaymentTiming, _full_name


def _fake_booking(with_agent: bool = True):
    now = datetime.now(timezone.utc)
    agent = SimpleNamespace(id=uuid4(), user=SimpleNamespace(first_name="Mario", last_name="Mario")) if with_agent else None
    return SimpleNamespace(
        id=uuid4(),
        customer_id=uuid4(),
        provider_id=uuid4(),
        service_id=uuid4(),
        field_agent_id=(agent.id if agent else None),
        scheduled_time=now,
        duration_minutes=60,
        description="Leaky tap in kitchen",
        status=BookingStatus.CONFIRMED,
        location_postcode="M1 1AD",
        location_address=None,
        base_price_cents=5000,
        deposit_paid_cents=0,
        total_paid_cents=0,
        payment_timing=PaymentTiming.BEFORE_SERVICE,
        deposit_percentage=0,
        promo_code=None,
        discount_cents=0,
        created_at=now,
        customer=SimpleNamespace(first_name="Alice", last_name="Springs", phone="555-0101"),
        service=SimpleNamespace(name="Emergency Plumbing", service_type="Plumbing"),
        field_agent=agent,
    )


def test_full_name_helper():
    assert _full_name(SimpleNamespace(first_name="A", last_name="B")) == "A B"
    assert _full_name(SimpleNamespace(first_name="Solo", last_name="")) == "Solo"
    assert _full_name(None) is None


def test_from_booking_enriches_display_fields():
    e = BookingReadEnriched.from_booking(_fake_booking())
    assert e.customer_name == "Alice Springs"
    assert e.customer_phone == "555-0101"
    assert e.service_name == "Emergency Plumbing"
    assert e.service_type == "Plumbing"
    assert e.assigned_agent_name == "Mario Mario"
    assert e.assigned_agent_id is not None
    # base BookingRead fields still carried through
    assert e.base_price_cents == 5000
    assert e.status == BookingStatus.CONFIRMED


def test_from_booking_handles_unassigned():
    e = BookingReadEnriched.from_booking(_fake_booking(with_agent=False))
    assert e.assigned_agent_id is None
    assert e.assigned_agent_name is None
    assert e.customer_name == "Alice Springs"
