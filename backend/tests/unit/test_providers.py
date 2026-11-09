"""
Unit tests for provider operations

"""

from uuid import uuid4

import pytest

from app.core.security import security_manager
from app.domain.booking.models import Provider
from app.domain.user.models import User, UserRole


@pytest.mark.asyncio
async def test_create_provider(db_session, test_tenant):
    """Test creating a provider"""
    user = User(
        id=uuid4(),
        tenant_id=test_tenant,
        email="fixture-04482d966ef7@example.test",
        hashed_password=security_manager.hash_password("Pass123!"),
        first_name="Test",
        last_name="Provider",
        role=UserRole.PROVIDER,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    provider = Provider(
        id=uuid4(),
        tenant_id=test_tenant,
        user_id=user.id,
        business_name="Test Business",
        is_active=True,
    )
    db_session.add(provider)
    await db_session.commit()
    await db_session.refresh(provider)

    assert provider.id is not None
    assert provider.business_name == "Test Business"


@pytest.mark.asyncio
async def test_get_provider_by_id(db_session, test_provider):
    """Test getting provider by ID"""
    from sqlalchemy import select

    result = await db_session.execute(select(Provider).where(Provider.id == test_provider))
    provider = result.scalar_one_or_none()

    assert provider is not None
    assert provider.id == test_provider


@pytest.mark.asyncio
async def test_update_provider_details(db_session, test_tenant, test_provider):
    """Test updating provider details"""
    from sqlalchemy import select

    result = await db_session.execute(select(Provider).where(Provider.id == test_provider))
    provider = result.scalar_one()

    provider.business_name = "Updated Business"
    provider.business_phone = "555-1234"
    await db_session.commit()
    await db_session.refresh(provider)

    assert provider.business_name == "Updated Business"
    assert provider.business_phone == "555-1234"


@pytest.mark.asyncio
async def test_deactivate_provider(db_session, test_provider):
    """Test deactivating a provider"""
    from sqlalchemy import select

    result = await db_session.execute(select(Provider).where(Provider.id == test_provider))
    provider = result.scalar_one()

    provider.is_active = False
    await db_session.commit()
    await db_session.refresh(provider)

    assert provider.is_active is False


@pytest.mark.asyncio
async def test_provider_with_service_radius(db_session, test_tenant, test_provider):
    """Test provider with service radius"""
    from sqlalchemy import select

    result = await db_session.execute(select(Provider).where(Provider.id == test_provider))
    provider = result.scalar_one()

    provider.service_radius_km = 25
    await db_session.commit()
    await db_session.refresh(provider)

    assert provider.service_radius_km == 25


@pytest.mark.asyncio
async def test_list_active_providers(db_session, test_tenant):
    """Test listing active providers"""
    from sqlalchemy import select

    # Create multiple providers
    for i in range(3):
        user = User(
            id=uuid4(),
            tenant_id=test_tenant,
            email=f"provider{i}@example.test",
            hashed_password=security_manager.hash_password("Pass123!"),
            first_name=f"Provider{i}",
            last_name="Test",
            role=UserRole.PROVIDER,
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()

        provider = Provider(
            id=uuid4(),
            tenant_id=test_tenant,
            user_id=user.id,
            business_name=f"Business {i}",
            is_active=True,
        )
        db_session.add(provider)

    await db_session.commit()

    result = await db_session.execute(select(Provider).where(Provider.tenant_id == test_tenant, Provider.is_active == True))
    providers = result.scalars().all()

    assert len(providers) >= 3


@pytest.mark.asyncio
async def test_provider_average_rating(db_session, test_provider):
    """Test provider average rating"""
    from sqlalchemy import select

    result = await db_session.execute(select(Provider).where(Provider.id == test_provider))
    provider = result.scalar_one()

    provider.average_rating = 4.5
    await db_session.commit()
    await db_session.refresh(provider)

    assert provider.average_rating == 4.5


@pytest.mark.asyncio
async def test_provider_business_contact(db_session, test_provider):
    """Test provider business contact info"""
    from sqlalchemy import select

    result = await db_session.execute(select(Provider).where(Provider.id == test_provider))
    provider = result.scalar_one()

    provider.business_email = "fixture-2ddaaf883a06@example.test"
    provider.business_phone = "555-9999"
    provider.website_url = "https://business.com"
    await db_session.commit()
    await db_session.refresh(provider)

    assert provider.business_email == "fixture-2ddaaf883a06@example.test"
    assert provider.business_phone == "555-9999"
    assert provider.website_url == "https://business.com"


@pytest.mark.asyncio
async def test_provider_description(db_session, test_provider):
    """Test provider description"""
    from sqlalchemy import select

    result = await db_session.execute(select(Provider).where(Provider.id == test_provider))
    provider = result.scalar_one()

    description = "Professional cleaning services with 10 years experience"
    provider.description = description
    await db_session.commit()
    await db_session.refresh(provider)

    assert provider.description == description


@pytest.mark.asyncio
async def test_get_providers_by_tenant(db_session, test_tenant, test_provider):
    """Test getting all providers for a tenant"""
    from sqlalchemy import select

    result = await db_session.execute(select(Provider).where(Provider.tenant_id == test_tenant))
    providers = result.scalars().all()

    assert len(providers) >= 1
    assert all(p.tenant_id == test_tenant for p in providers)
