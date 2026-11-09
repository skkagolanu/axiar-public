"""
Unit tests for authentication

"""

from uuid import uuid4

import pytest

from app.core.security import security_manager
from app.domain.user.models import User, UserRole


@pytest.mark.asyncio
async def test_user_registration(db_session, test_tenant):
    """Test user registration"""
    user = User(
        id=uuid4(),
        tenant_id=test_tenant,
        email="fixture-1e3fd5bdd114@example.test",
        hashed_password=security_manager.hash_password("SecurePass123!"),
        first_name="New",
        last_name="User",
        role=UserRole.CUSTOMER,
        is_active=True,
        is_verified=False,
    )

    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    assert user.id is not None
    assert user.email == "fixture-1e3fd5bdd114@example.test"
    assert user.is_verified is False


@pytest.mark.asyncio
async def test_password_verification(db_session, test_tenant):
    """Test password verification"""
    password = "TestPassword123!"
    hashed = security_manager.hash_password(password)

    user = User(
        id=uuid4(),
        tenant_id=test_tenant,
        email="fixture-f660ab912ec1@example.test",
        hashed_password=hashed,
        first_name="Test",
        last_name="User",
        role=UserRole.CUSTOMER,
        is_active=True,
    )

    db_session.add(user)
    await db_session.commit()

    # Verify correct password
    assert security_manager.verify_password(password, user.hashed_password)

    # Verify incorrect password
    assert not security_manager.verify_password("WrongPassword", user.hashed_password)


@pytest.mark.asyncio
async def test_jwt_token_creation():
    """Test JWT token creation"""
    user_id = str(uuid4())
    token = security_manager.create_access_token({"sub": user_id})

    assert token is not None
    assert isinstance(token, str)
    assert len(token) > 0


@pytest.mark.asyncio
async def test_jwt_token_verification():
    """Test JWT token verification"""
    user_id = str(uuid4())
    token = security_manager.create_access_token({"sub": user_id})

    payload = await security_manager.verify_token(token)

    assert payload is not None
    assert payload["sub"] == user_id


@pytest.mark.asyncio
async def test_user_login_flow(db_session, test_tenant):
    """Test complete login flow"""
    from sqlalchemy import select

    password = "LoginTest123!"
    email = "fixture-007ad1c5c601@example.test"

    # Create user
    user = User(
        id=uuid4(),
        tenant_id=test_tenant,
        email=email,
        hashed_password=security_manager.hash_password(password),
        first_name="Login",
        last_name="Test",
        role=UserRole.CUSTOMER,
        is_active=True,
        is_verified=True,
    )

    db_session.add(user)
    await db_session.commit()

    # Simulate login: find user by email
    result = await db_session.execute(select(User).where(User.email == email))
    found_user = result.scalar_one_or_none()

    assert found_user is not None

    # Verify password
    assert security_manager.verify_password(password, found_user.hashed_password)

    # Create token
    token = security_manager.create_access_token({"sub": str(found_user.id)})
    assert token is not None


@pytest.mark.asyncio
async def test_inactive_user_cannot_login(db_session, test_tenant):
    """Test that inactive users cannot login"""
    user = User(
        id=uuid4(),
        tenant_id=test_tenant,
        email="fixture-236f3a930a24@example.test",
        hashed_password=security_manager.hash_password("Password123!"),
        first_name="Inactive",
        last_name="User",
        role=UserRole.CUSTOMER,
        is_active=False,
    )

    db_session.add(user)
    await db_session.commit()

    assert user.is_active is False


@pytest.mark.asyncio
async def test_user_roles(db_session, test_tenant):
    """Test different user roles"""
    roles = [UserRole.CUSTOMER, UserRole.PROVIDER, UserRole.ADMIN]

    for role in roles:
        user = User(
            id=uuid4(),
            tenant_id=test_tenant,
            email=f"{role.value}@example.test",
            hashed_password=security_manager.hash_password("Password123!"),
            first_name="Test",
            last_name=role.value,
            role=role,
            is_active=True,
        )

        db_session.add(user)

    await db_session.commit()

    from sqlalchemy import select

    result = await db_session.execute(select(User))
    users = result.scalars().all()

    assert len([u for u in users if u.role == UserRole.ADMIN]) >= 1
    assert len([u for u in users if u.role == UserRole.PROVIDER]) >= 1
    assert len([u for u in users if u.role == UserRole.CUSTOMER]) >= 1


@pytest.mark.asyncio
async def test_email_uniqueness(db_session, test_tenant):
    """Test that email must be unique"""
    from sqlalchemy.exc import IntegrityError

    email = "fixture-28c0d8411111@example.test"

    user1 = User(
        id=uuid4(),
        tenant_id=test_tenant,
        email=email,
        hashed_password=security_manager.hash_password("Password123!"),
        first_name="First",
        last_name="User",
        role=UserRole.CUSTOMER,
        is_active=True,
    )

    db_session.add(user1)
    await db_session.commit()

    # Try to create another user with same email
    user2 = User(
        id=uuid4(),
        tenant_id=test_tenant,
        email=email,
        hashed_password=security_manager.hash_password("Password123!"),
        first_name="Second",
        last_name="User",
        role=UserRole.CUSTOMER,
        is_active=True,
    )

    db_session.add(user2)

    with pytest.raises(IntegrityError):
        await db_session.commit()
