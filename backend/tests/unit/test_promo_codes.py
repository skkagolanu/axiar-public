"""
Unit tests for promotional codes system
Coverage target: 80%+
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.core.tenant_context import set_current_tenant
from app.domain.promo.models import PromoCode
from app.domain.promo.repository import PromoCodeRepository


@pytest.mark.asyncio
async def test_create_promo_code(db_session, default_tenant_id):
    """Test creating a promo code"""
    set_current_tenant(default_tenant_id)
    repo = PromoCodeRepository(db_session)

    promo = PromoCode(
        code="TEST20",
        discount_type="percentage",
        discount_value=20,
        max_uses=100,
        min_purchase_cents=1000,
        valid_from=datetime.now(timezone.utc),
        valid_until=datetime.now(timezone.utc) + timedelta(days=30),
    )

    created = await repo.create(promo)
    await db_session.commit()

    assert created.code == "TEST20"
    assert created.discount_value == 20
    assert created.current_uses == 0


@pytest.mark.asyncio
async def test_validate_promo_code_success(db_session, default_tenant_id):
    """Test validating a valid promo code"""
    set_current_tenant(default_tenant_id)
    repo = PromoCodeRepository(db_session)

    promo = PromoCode(
        code="VALID20",
        discount_type="percentage",
        discount_value=20,
        max_uses=10,
        min_purchase_cents=1000,
        valid_from=datetime.now(timezone.utc) - timedelta(days=1),
        valid_until=datetime.now(timezone.utc) + timedelta(days=30),
        is_active=True,
    )
    await repo.create(promo)
    await db_session.commit()

    valid, discount, message = await repo.validate_and_apply("VALID20", 5000)

    assert valid is True
    assert discount == 1000  # 20% of 5000
    assert "success" in message.lower()


@pytest.mark.asyncio
async def test_validate_promo_code_expired(db_session, default_tenant_id):
    """Test validating an expired promo code"""
    set_current_tenant(default_tenant_id)
    repo = PromoCodeRepository(db_session)

    promo = PromoCode(
        code="EXPIRED",
        discount_type="percentage",
        discount_value=20,
        max_uses=10,
        min_purchase_cents=1000,
        valid_from=datetime.now(timezone.utc) - timedelta(days=60),
        valid_until=datetime.now(timezone.utc) - timedelta(days=1),
        is_active=True,
    )
    await repo.create(promo)
    await db_session.commit()

    valid, discount, message = await repo.validate_and_apply("EXPIRED", 5000)

    assert valid is False
    assert discount == 0
    assert "expired" in message.lower()


@pytest.mark.asyncio
async def test_validate_promo_code_min_purchase(db_session, default_tenant_id):
    """Test promo code with minimum purchase requirement"""
    set_current_tenant(default_tenant_id)
    repo = PromoCodeRepository(db_session)

    promo = PromoCode(
        code="MIN100",
        discount_type="fixed_amount",
        discount_value=500,
        max_uses=10,
        min_purchase_cents=10000,
        valid_from=datetime.now(timezone.utc),
        valid_until=datetime.now(timezone.utc) + timedelta(days=30),
        is_active=True,
    )
    await repo.create(promo)
    await db_session.commit()

    # Below minimum
    valid, discount, message = await repo.validate_and_apply("MIN100", 5000)
    assert valid is False
    assert "minimum" in message.lower()

    # Above minimum
    valid, discount, message = await repo.validate_and_apply("MIN100", 15000)
    assert valid is True
    assert discount == 500


@pytest.mark.asyncio
async def test_promo_code_usage_limit(db_session, default_tenant_id):
    """Test promo code usage limit"""
    set_current_tenant(default_tenant_id)
    repo = PromoCodeRepository(db_session)

    promo = PromoCode(
        code="LIMITED",
        discount_type="percentage",
        discount_value=10,
        max_uses=2,
        min_purchase_cents=0,
        valid_from=datetime.now(timezone.utc),
        valid_until=datetime.now(timezone.utc) + timedelta(days=30),
        is_active=True,
        current_uses=2,  # Already at limit
    )
    await repo.create(promo)
    await db_session.commit()

    valid, discount, message = await repo.validate_and_apply("LIMITED", 5000)

    assert valid is False
    assert "limit" in message.lower()


@pytest.mark.asyncio
async def test_increment_promo_usage(db_session, default_tenant_id):
    """Test incrementing promo code usage"""
    set_current_tenant(default_tenant_id)
    repo = PromoCodeRepository(db_session)

    promo = PromoCode(
        code="INCREMENT",
        discount_type="percentage",
        discount_value=10,
        max_uses=10,
        min_purchase_cents=0,
        valid_from=datetime.now(timezone.utc),
        valid_until=datetime.now(timezone.utc) + timedelta(days=30),
        is_active=True,
        current_uses=0,
    )
    await repo.create(promo)
    await db_session.commit()

    await repo.increment_usage("INCREMENT")
    await db_session.commit()

    updated = await repo.get_by_code("INCREMENT")
    assert updated.current_uses == 1
