"""
Unit tests for customer management

"""

from uuid import uuid4

import pytest

from app.domain.user.models import User, UserRole


@pytest.mark.asyncio
async def test_create_customer(db_session, test_tenant):
    """Test creating a customer"""
    customer = User(
        id=uuid4(),
        tenant_id=test_tenant,
        email="fixture-c5da3c33a03b@example.test",
        hashed_password="hashed",
        first_name="Test",
        last_name="Customer",
        role=UserRole.CUSTOMER,
        is_active=True,
    )

    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)

    assert customer.id is not None
    assert customer.role == UserRole.CUSTOMER


@pytest.mark.asyncio
async def test_get_customer_by_id(db_session, test_customer):
    """Test getting customer by ID"""
    from sqlalchemy import select

    result = await db_session.execute(select(User).where(User.id == test_customer))
    customer = result.scalar_one_or_none()

    assert customer is not None
    assert customer.id == test_customer


@pytest.mark.asyncio
async def test_update_customer_profile(db_session, test_customer):
    """Test updating customer profile"""
    from sqlalchemy import select

    result = await db_session.execute(select(User).where(User.id == test_customer))
    customer = result.scalar_one()

    customer.first_name = "Updated"
    customer.phone = "+1234567890"
    await db_session.commit()
    await db_session.refresh(customer)

    assert customer.first_name == "Updated"
    assert customer.phone == "+1234567890"


@pytest.mark.asyncio
async def test_deactivate_customer(db_session, test_customer):
    """Test deactivating a customer"""
    from sqlalchemy import select

    result = await db_session.execute(select(User).where(User.id == test_customer))
    customer = result.scalar_one()

    customer.is_active = False
    await db_session.commit()

    assert customer.is_active is False


@pytest.mark.asyncio
async def test_list_customers_by_tenant(db_session, test_tenant):
    """Test listing all customers in a tenant"""
    from sqlalchemy import select

    for i in range(3):
        customer = User(
            id=uuid4(),
            tenant_id=test_tenant,
            email=f"customer{i}@example.test",
            hashed_password="hashed",
            first_name=f"Customer",
            last_name=f"{i}",
            role=UserRole.CUSTOMER,
        )
        db_session.add(customer)

    await db_session.commit()

    result = await db_session.execute(select(User).where(User.tenant_id == test_tenant, User.role == UserRole.CUSTOMER))
    customers = result.scalars().all()

    assert len(customers) >= 3


@pytest.mark.asyncio
async def test_customer_email_unique(db_session, test_tenant):
    """Test customer email uniqueness"""
    from sqlalchemy.exc import IntegrityError

    customer1 = User(
        id=uuid4(),
        tenant_id=test_tenant,
        email="fixture-28c0d8411111@example.test",
        hashed_password="hashed",
        first_name="Customer",
        last_name="1",
        role=UserRole.CUSTOMER,
    )
    db_session.add(customer1)
    await db_session.commit()

    customer2 = User(
        id=uuid4(),
        tenant_id=test_tenant,
        email="fixture-28c0d8411111@example.test",
        hashed_password="hashed",
        first_name="Customer",
        last_name="2",
        role=UserRole.CUSTOMER,
    )
    db_session.add(customer2)

    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_customer_contact_info(db_session, test_tenant):
    """Test customer contact information"""
    customer = User(
        id=uuid4(),
        tenant_id=test_tenant,
        email="fixture-92a059e0310b@example.test",
        hashed_password="hashed",
        first_name="Contact",
        last_name="Test",
        role=UserRole.CUSTOMER,
        phone="+1234567890",
    )

    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)

    assert customer.phone == "+1234567890"


@pytest.mark.asyncio
async def test_search_customer_by_email(db_session, test_tenant):
    """Test searching customer by email"""
    from sqlalchemy import select

    email = "fixture-52c53807d318@example.test"
    customer = User(
        id=uuid4(),
        tenant_id=test_tenant,
        email=email,
        hashed_password="hashed",
        first_name="Search",
        last_name="Test",
        role=UserRole.CUSTOMER,
    )
    db_session.add(customer)
    await db_session.commit()

    result = await db_session.execute(select(User).where(User.email == email))
    found = result.scalar_one_or_none()

    assert found is not None
    assert found.email == email


@pytest.mark.asyncio
async def test_customer_verification_status(db_session, test_tenant):
    """Test customer verification status"""
    customer = User(
        id=uuid4(),
        tenant_id=test_tenant,
        email="fixture-94c11bd3cd68@example.test",
        hashed_password="hashed",
        first_name="Verified",
        last_name="Test",
        role=UserRole.CUSTOMER,
        is_verified=True,
    )

    db_session.add(customer)
    await db_session.commit()

    assert customer.is_verified is True


@pytest.mark.asyncio
async def test_list_active_customers(db_session, test_tenant):
    """Test listing only active customers"""
    from sqlalchemy import select

    for i in range(2):
        customer = User(
            id=uuid4(),
            tenant_id=test_tenant,
            email=f"active{i}@example.test",
            hashed_password="hashed",
            first_name="Active",
            last_name=f"{i}",
            role=UserRole.CUSTOMER,
            is_active=True,
        )
        db_session.add(customer)

    inactive = User(
        id=uuid4(),
        tenant_id=test_tenant,
        email="fixture-236f3a930a24@example.test",
        hashed_password="hashed",
        first_name="Inactive",
        last_name="Test",
        role=UserRole.CUSTOMER,
        is_active=False,
    )
    db_session.add(inactive)
    await db_session.commit()

    result = await db_session.execute(
        select(User).where(
            User.tenant_id == test_tenant,
            User.role == UserRole.CUSTOMER,
            User.is_active == True,
        )
    )
    active_customers = result.scalars().all()

    assert len(active_customers) >= 2
    assert all(c.is_active for c in active_customers)
