"""
Unit tests for referral system

"""

from uuid import uuid4

import pytest

from app.core.tenant_context import set_current_tenant
from app.domain.referral.models import Referral
from app.domain.referral.repository import ReferralRepository, generate_referral_code


async def create_test_users(db_session, test_tenant):
    """Helper to create test users"""
    from app.core.security import security_manager
    from app.domain.user.models import User, UserRole

    referrer = User(
        id=uuid4(),
        tenant_id=test_tenant,
        email=f"referrer_{uuid4().hex[:8]}@example.test",
        hashed_password=security_manager.hash_password("test123"),
        first_name="Test",
        last_name="Referrer",
        role=UserRole.CUSTOMER,
        is_active=True,
    )
    referred = User(
        id=uuid4(),
        tenant_id=test_tenant,
        email=f"referred_{uuid4().hex[:8]}@example.test",
        hashed_password=security_manager.hash_password("test123"),
        first_name="Test",
        last_name="Referred",
        role=UserRole.CUSTOMER,
        is_active=True,
    )
    db_session.add(referrer)
    db_session.add(referred)
    await db_session.commit()
    return referrer, referred


@pytest.mark.asyncio
async def test_create_referral(db_session, test_tenant):
    """Test creating a referral"""
    set_current_tenant(test_tenant)
    referrer, referred = await create_test_users(db_session, test_tenant)

    repo = ReferralRepository(db_session)
    referral = await repo.create(referrer.id, referred.id, "REF12345")
    await db_session.commit()

    assert referral.referrer_id == referrer.id
    assert referral.referred_id == referred.id
    assert referral.referral_code == "REF12345"
    assert referral.is_rewarded is False


@pytest.mark.asyncio
async def test_get_referral_by_code(db_session, test_tenant):
    """Test getting referral by code"""
    set_current_tenant(test_tenant)
    referrer, referred = await create_test_users(db_session, test_tenant)

    repo = ReferralRepository(db_session)
    await repo.create(referrer.id, referred.id, "TESTCODE")
    await db_session.commit()

    found = await repo.get_by_code("TESTCODE")
    assert found is not None
    assert found.referral_code == "TESTCODE"


@pytest.mark.asyncio
async def test_get_user_referrals(db_session, test_tenant):
    """Test getting all referrals for a user"""
    set_current_tenant(test_tenant)
    referrer, _ = await create_test_users(db_session, test_tenant)

    repo = ReferralRepository(db_session)

    # Create multiple referrals
    for i in range(3):
        referred = await create_test_users(db_session, test_tenant)
        await repo.create(referrer.id, referred[1].id, f"CODE{i}")

    await db_session.commit()

    referrals = await repo.get_user_referrals(referrer.id)
    assert len(referrals) == 3


@pytest.mark.asyncio
async def test_get_referral_stats(db_session, test_tenant):
    """Test getting referral statistics"""
    set_current_tenant(test_tenant)
    referrer, _ = await create_test_users(db_session, test_tenant)
    code = "STATSCODE"

    repo = ReferralRepository(db_session)

    # Create referrals with different reward states
    ref1_user = await create_test_users(db_session, test_tenant)
    ref2_user = await create_test_users(db_session, test_tenant)
    ref3_user = await create_test_users(db_session, test_tenant)

    ref1 = await repo.create(referrer.id, ref1_user[1].id, code)
    ref2 = await repo.create(referrer.id, ref2_user[1].id, code)
    ref3 = await repo.create(referrer.id, ref3_user[1].id, code)
    await db_session.commit()

    # Mark some as rewarded
    await repo.mark_rewarded(ref1.id, 1000)
    await repo.mark_rewarded(ref2.id, 1500)
    await db_session.commit()

    stats = await repo.get_stats(referrer.id, code)

    assert stats["total_referrals"] == 3
    assert stats["successful_referrals"] == 2
    assert stats["total_rewards_cents"] == 2500
    assert stats["referral_code"] == code


@pytest.mark.asyncio
async def test_mark_referral_rewarded(db_session, test_tenant):
    """Test marking referral as rewarded"""
    set_current_tenant(test_tenant)
    referrer, referred = await create_test_users(db_session, test_tenant)

    repo = ReferralRepository(db_session)
    referral = await repo.create(referrer.id, referred.id, "REWARD")
    await db_session.commit()

    await repo.mark_rewarded(referral.id, 2000)
    await db_session.commit()

    updated = await repo.get_by_code("REWARD")
    assert updated.is_rewarded is True
    assert updated.reward_cents == 2000


def test_generate_referral_code():
    """Test referral code generation"""
    code1 = generate_referral_code()
    code2 = generate_referral_code()

    assert len(code1) == 8
    assert len(code2) == 8
    assert code1 != code2  # Should be unique
    assert code1.isupper()  # Should be uppercase
