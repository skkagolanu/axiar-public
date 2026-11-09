"""
Unit tests for service management

"""

from uuid import uuid4

import pytest

from app.domain.booking.models import Service


@pytest.mark.asyncio
async def test_create_service(db_session, test_tenant, test_provider):
    """Test creating a service"""
    service = Service(
        id=uuid4(),
        tenant_id=test_tenant,
        provider_id=test_provider,
        service_type="cleaning",
        name="House Cleaning",
        description="Professional cleaning",
        base_price_cents=5000,
        duration_minutes=120,
    )

    db_session.add(service)
    await db_session.commit()
    await db_session.refresh(service)

    assert service.id is not None
    assert service.name == "House Cleaning"


@pytest.mark.asyncio
async def test_get_service_by_id(db_session, test_service):
    """Test getting service by ID"""
    from sqlalchemy import select

    result = await db_session.execute(select(Service).where(Service.id == test_service))
    service = result.scalar_one_or_none()

    assert service is not None
    assert service.id == test_service


@pytest.mark.asyncio
async def test_update_service(db_session, test_service):
    """Test updating service details"""
    from sqlalchemy import select

    result = await db_session.execute(select(Service).where(Service.id == test_service))
    service = result.scalar_one()

    service.name = "Updated Service"
    service.base_price_cents = 7500
    await db_session.commit()
    await db_session.refresh(service)

    assert service.name == "Updated Service"
    assert service.base_price_cents == 7500


@pytest.mark.asyncio
async def test_deactivate_service(db_session, test_service):
    """Test deactivating a service"""
    from sqlalchemy import select

    result = await db_session.execute(select(Service).where(Service.id == test_service))
    service = result.scalar_one()

    service.is_available = False
    await db_session.commit()

    assert service.is_available is False


@pytest.mark.asyncio
async def test_list_services_by_provider(db_session, test_tenant, test_provider):
    """Test listing services by provider"""
    from sqlalchemy import select

    for i in range(3):
        service = Service(
            id=uuid4(),
            tenant_id=test_tenant,
            provider_id=test_provider,
            service_type="cleaning",
            name=f"Service {i}",
            description="Test service",
            base_price_cents=5000,
            duration_minutes=60,
        )
        db_session.add(service)

    await db_session.commit()

    result = await db_session.execute(select(Service).where(Service.provider_id == test_provider))
    services = result.scalars().all()

    assert len(services) >= 3


@pytest.mark.asyncio
async def test_list_services_by_tenant(db_session, test_tenant, test_provider):
    """Test listing services by tenant"""
    from sqlalchemy import select

    for i in range(2):
        service = Service(
            id=uuid4(),
            tenant_id=test_tenant,
            provider_id=test_provider,
            service_type="cleaning",
            name=f"Tenant Service {i}",
            description="Test",
            base_price_cents=5000,
            duration_minutes=60,
        )
        db_session.add(service)

    await db_session.commit()

    result = await db_session.execute(select(Service).where(Service.tenant_id == test_tenant))
    services = result.scalars().all()

    assert len(services) >= 2


@pytest.mark.asyncio
async def test_service_pricing(db_session, test_tenant, test_provider):
    """Test service pricing"""
    service = Service(
        id=uuid4(),
        tenant_id=test_tenant,
        provider_id=test_provider,
        service_type="premium",
        name="Premium Service",
        description="High-end service",
        base_price_cents=15000,
        duration_minutes=180,
    )

    db_session.add(service)
    await db_session.commit()
    await db_session.refresh(service)

    assert service.base_price_cents == 15000
    assert service.duration_minutes == 180


@pytest.mark.asyncio
async def test_list_available_services(db_session, test_tenant, test_provider):
    """Test listing only available services"""
    from sqlalchemy import select

    active = Service(
        id=uuid4(),
        tenant_id=test_tenant,
        provider_id=test_provider,
        service_type="cleaning",
        name="Available Service",
        description="Available",
        base_price_cents=5000,
        duration_minutes=60,
        is_available=True,
    )
    db_session.add(active)

    inactive = Service(
        id=uuid4(),
        tenant_id=test_tenant,
        provider_id=test_provider,
        service_type="cleaning",
        name="Unavailable Service",
        description="Unavailable",
        base_price_cents=5000,
        duration_minutes=60,
        is_available=False,
    )
    db_session.add(inactive)
    await db_session.commit()

    result = await db_session.execute(
        select(Service).where(Service.provider_id == test_provider, Service.is_available == True)
    )
    available_services = result.scalars().all()

    assert len(available_services) >= 1
    assert all(s.is_available for s in available_services)
