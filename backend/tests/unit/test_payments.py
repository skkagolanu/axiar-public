"""
Unit tests for payment system

"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.domain.booking.models import Booking
from app.domain.payment.models import Payment, PaymentMethod, PaymentStatus


@pytest.fixture
async def test_booking_for_payment(db_session, test_tenant, test_customer, test_provider, test_service):
    """Create a test booking for payments"""
    booking = Booking(
        id=uuid4(),
        tenant_id=test_tenant,
        customer_id=test_customer,
        provider_id=test_provider,
        service_id=test_service,
        scheduled_time=datetime.now(timezone.utc) + timedelta(days=1),
        duration_minutes=60,
        location_postcode="12345",
        base_price_cents=10000,
    )
    db_session.add(booking)
    await db_session.commit()
    await db_session.refresh(booking)
    return booking.id


@pytest.mark.asyncio
async def test_create_payment(db_session, test_tenant, test_booking_for_payment):
    """Test creating a payment"""
    payment = Payment(
        id=uuid4(),
        tenant_id=test_tenant,
        booking_id=test_booking_for_payment,
        amount_cents=10000,
        currency="GBP",
        status=PaymentStatus.PENDING,
        method=PaymentMethod.CARD,
    )

    db_session.add(payment)
    await db_session.commit()
    await db_session.refresh(payment)

    assert payment.id is not None
    assert payment.amount_cents == 10000
    assert payment.status == PaymentStatus.PENDING


@pytest.mark.asyncio
async def test_payment_status_transitions(db_session, test_tenant, test_booking_for_payment):
    """Test payment status transitions"""
    from sqlalchemy import select

    payment = Payment(
        id=uuid4(),
        tenant_id=test_tenant,
        booking_id=test_booking_for_payment,
        amount_cents=5000,
        method=PaymentMethod.CARD,
        status=PaymentStatus.PENDING,
    )
    db_session.add(payment)
    await db_session.commit()

    # Transition to processing
    payment.status = PaymentStatus.PROCESSING
    await db_session.commit()
    assert payment.status == PaymentStatus.PROCESSING

    # Transition to succeeded
    payment.status = PaymentStatus.SUCCEEDED
    payment.processed_at = datetime.now(timezone.utc)
    await db_session.commit()
    assert payment.status == PaymentStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_payment_methods(db_session, test_tenant, test_booking_for_payment):
    """Test different payment methods"""
    methods = [PaymentMethod.CARD, PaymentMethod.BANK_TRANSFER, PaymentMethod.CASH]

    for method in methods:
        payment = Payment(
            id=uuid4(),
            tenant_id=test_tenant,
            booking_id=test_booking_for_payment,
            amount_cents=5000,
            method=method,
        )
        db_session.add(payment)

    await db_session.commit()

    from sqlalchemy import select

    result = await db_session.execute(select(Payment).where(Payment.booking_id == test_booking_for_payment))
    payments = result.scalars().all()

    assert len(payments) >= 3


@pytest.mark.asyncio
async def test_failed_payment(db_session, test_tenant, test_booking_for_payment):
    """Test failed payment handling"""
    payment = Payment(
        id=uuid4(),
        tenant_id=test_tenant,
        booking_id=test_booking_for_payment,
        amount_cents=5000,
        method=PaymentMethod.CARD,
        status=PaymentStatus.FAILED,
        failure_reason="Insufficient funds",
    )

    db_session.add(payment)
    await db_session.commit()
    await db_session.refresh(payment)

    assert payment.status == PaymentStatus.FAILED
    assert payment.failure_reason == "Insufficient funds"


@pytest.mark.asyncio
async def test_refunded_payment(db_session, test_tenant, test_booking_for_payment):
    """Test refunded payment"""
    payment = Payment(
        id=uuid4(),
        tenant_id=test_tenant,
        booking_id=test_booking_for_payment,
        amount_cents=10000,
        method=PaymentMethod.CARD,
        status=PaymentStatus.SUCCEEDED,
    )
    db_session.add(payment)
    await db_session.commit()

    # Refund
    payment.status = PaymentStatus.REFUNDED
    await db_session.commit()

    assert payment.status == PaymentStatus.REFUNDED


@pytest.mark.asyncio
async def test_payment_with_stripe_id(db_session, test_tenant, test_booking_for_payment):
    """Test payment with Stripe integration"""
    payment = Payment(
        id=uuid4(),
        tenant_id=test_tenant,
        booking_id=test_booking_for_payment,
        amount_cents=5000,
        method=PaymentMethod.CARD,
        stripe_payment_intent_id="pi_test123",
        stripe_charge_id="ch_test123",
    )

    db_session.add(payment)
    await db_session.commit()
    await db_session.refresh(payment)

    assert payment.stripe_payment_intent_id == "pi_test123"
    assert payment.stripe_charge_id == "ch_test123"


@pytest.mark.asyncio
async def test_payment_metadata(db_session, test_tenant, test_booking_for_payment):
    """Test payment metadata storage"""
    metadata = {"customer_ip": "192.168.1.1", "device": "mobile"}

    payment = Payment(
        id=uuid4(),
        tenant_id=test_tenant,
        booking_id=test_booking_for_payment,
        amount_cents=5000,
        method=PaymentMethod.CARD,
        payment_metadata=metadata,
    )

    db_session.add(payment)
    await db_session.commit()
    await db_session.refresh(payment)

    assert payment.payment_metadata == metadata


@pytest.mark.asyncio
async def test_list_payments_by_booking(db_session, test_tenant, test_booking_for_payment):
    """Test listing payments for a booking"""
    from sqlalchemy import select

    for i in range(2):
        payment = Payment(
            id=uuid4(),
            tenant_id=test_tenant,
            booking_id=test_booking_for_payment,
            amount_cents=5000,
            method=PaymentMethod.CARD,
        )
        db_session.add(payment)

    await db_session.commit()

    result = await db_session.execute(select(Payment).where(Payment.booking_id == test_booking_for_payment))
    payments = result.scalars().all()

    assert len(payments) >= 2


@pytest.mark.asyncio
async def test_payment_currency(db_session, test_tenant, test_booking_for_payment):
    """Test payment with different currencies"""
    payment = Payment(
        id=uuid4(),
        tenant_id=test_tenant,
        booking_id=test_booking_for_payment,
        amount_cents=5000,
        currency="USD",
        method=PaymentMethod.CARD,
    )

    db_session.add(payment)
    await db_session.commit()
    await db_session.refresh(payment)

    assert payment.currency == "USD"


@pytest.mark.asyncio
async def test_cancelled_payment(db_session, test_tenant, test_booking_for_payment):
    """Test cancelled payment"""
    payment = Payment(
        id=uuid4(),
        tenant_id=test_tenant,
        booking_id=test_booking_for_payment,
        amount_cents=5000,
        method=PaymentMethod.CARD,
        status=PaymentStatus.PENDING,
    )
    db_session.add(payment)
    await db_session.commit()

    payment.status = PaymentStatus.CANCELLED
    await db_session.commit()

    assert payment.status == PaymentStatus.CANCELLED


@pytest.mark.asyncio
async def test_list_succeeded_payments(db_session, test_tenant, test_booking_for_payment):
    """Test listing only succeeded payments"""
    from sqlalchemy import select

    succeeded = Payment(
        id=uuid4(),
        tenant_id=test_tenant,
        booking_id=test_booking_for_payment,
        amount_cents=5000,
        method=PaymentMethod.CARD,
        status=PaymentStatus.SUCCEEDED,
    )
    db_session.add(succeeded)

    failed = Payment(
        id=uuid4(),
        tenant_id=test_tenant,
        booking_id=test_booking_for_payment,
        amount_cents=5000,
        method=PaymentMethod.CARD,
        status=PaymentStatus.FAILED,
    )
    db_session.add(failed)
    await db_session.commit()

    result = await db_session.execute(
        select(Payment).where(
            Payment.booking_id == test_booking_for_payment,
            Payment.status == PaymentStatus.SUCCEEDED,
        )
    )
    succeeded_payments = result.scalars().all()

    assert len(succeeded_payments) >= 1
    assert all(p.status == PaymentStatus.SUCCEEDED for p in succeeded_payments)
