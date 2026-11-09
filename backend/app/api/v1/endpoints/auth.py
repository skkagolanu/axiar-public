import secrets
from typing import Dict
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_manager as cache
from app.core.config import settings
from app.core.database import get_db_session
from app.core.security import security_manager
from app.core.tenant_context import get_current_tenant
from app.domain.tenant.models import Tenant
from app.domain.user.models import User
from app.domain.user.repository import UserRepository
from app.domain.user.schemas import MagicLinkRequest, TokenResponse, UserCreate, UserLogin, UserLoginResponse, UserRead
from app.services.notification_service import notification_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserRead, status_code=201)
async def register(user_data: UserCreate, session: AsyncSession = Depends(get_db_session)):
    'Register new user.'
    if user_data.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot self-register as admin",
        )

    # Check if user exists
    result = await session.execute(select(User).where(User.email == user_data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    # Registration must honor the same tenant resolved by middleware that login
    # later enforces. Headerless public signup retains the default-tenant fallback.
    current_tenant_id = get_current_tenant()
    tenant_query = (
        select(Tenant).where(Tenant.id == current_tenant_id)
        if current_tenant_id
        else select(Tenant).where(Tenant.slug == "default")
    )
    tenant_result = await session.execute(tenant_query)
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Resolved tenant not found")

    # Create user
    hashed_password = security_manager.hash_password(user_data.password)
    user = User(
        id=uuid4(),
        tenant_id=tenant.id,
        email=user_data.email,
        hashed_password=hashed_password,
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        phone=user_data.phone,
        role=user_data.role,
    )

    session.add(user)
    await session.commit()
    await session.refresh(user)

    return user


@router.post("/login", response_model=UserLoginResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), session: AsyncSession = Depends(get_db_session)):
    """Login user.

    The resolved request tenant (from ``X-Tenant-ID`` / ``X-Tenant-Slug``) is
    authoritative: email is looked up across tenants, but login is rejected if
    the user does not belong to the current tenant.
    """
    # Look up user by email across tenants (required for login)
    user_repo = UserRepository(session)
    user = await user_repo.get_by_email(form_data.username)

    # Passwordless accounts do not have a password hash; reject password login
    # without disclosing whether the account exists.
    if not user or not user.hashed_password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")

    if not security_manager.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")

    # Enforce tenant-bound login
    current_tenant_id = get_current_tenant()
    if current_tenant_id and user.tenant_id != current_tenant_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found in tenant")

    tenant_claim = str(user.tenant_id)

    # Create tokens bound to the user's tenant
    access_token = security_manager.create_access_token({"sub": str(user.id)}, extra_claims={"tenant_id": tenant_claim})
    refresh_token = security_manager.create_refresh_token(str(user.id), tenant_id=tenant_claim)

    return UserLoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=1800,
        user=user,
    )


@router.post("/magic-link", response_model=Dict[str, str])
async def request_magic_link(request: MagicLinkRequest, session: AsyncSession = Depends(get_db_session)):
    """Request a magic link for passwordless authentication"""
    magic_token = secrets.token_urlsafe(32)

    # Store token in cache for 15 minutes
    await cache.set(f"magic_link:{magic_token}", request.email, ttl=900)

    # Deliver the link by email only — never return the token in the API response
    # (returning it would let any caller authenticate as the requested email).
    magic_link = f"{settings.FRONTEND_URL}/auth/magic?token={magic_token}"
    await notification_service.send_email(
        to_email=request.email,
        subject="Your login link",
        body=f'<p><a href="{magic_link}">Click here to log in</a>. This link expires in 15 minutes.</p>',
    )

    return {"message": "If an account exists for that email, a magic link has been sent."}


@router.post("/verify-magic-link", response_model=TokenResponse)
async def verify_magic_link(token: str, session: AsyncSession = Depends(get_db_session)):
    """Verify magic link and create/login user"""
    # Retrieve email from cache
    email = await cache.get(f"magic_link:{token}")
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired magic link")

    # Get or create user
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        # Get default tenant
        from app.domain.tenant.models import Tenant

        tenant_result = await session.execute(select(Tenant).where(Tenant.slug == "default"))
        tenant = tenant_result.scalar_one_or_none()
        if not tenant:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Default tenant not found")

        # Create new user
        user = User(
            id=uuid4(), tenant_id=tenant.id, email=email, first_name="", last_name="", role="customer", is_verified=True
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    # Clean up token
    await cache.delete(f"magic_link:{token}")

    # Create tokens bound to the user's tenant
    tenant_claim = str(user.tenant_id)
    access_token = security_manager.create_access_token({"sub": str(user.id)}, extra_claims={"tenant_id": tenant_claim})
    refresh_token = security_manager.create_refresh_token(str(user.id), tenant_id=tenant_claim)

    return TokenResponse(access_token=access_token, refresh_token=refresh_token, expires_in=1800)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(refresh_token: str, session: AsyncSession = Depends(get_db_session)):
    """Issue a fresh access token after reloading and validating the user account."""
    payload = await security_manager.verify_token(refresh_token, expected_type="refresh")
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    tenant_id = payload.get("tenant_id")
    if tenant_id and str(user.tenant_id) != tenant_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    current_tenant_id = get_current_tenant()
    if current_tenant_id and user.tenant_id != current_tenant_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    extra_claims = {"tenant_id": str(user.tenant_id)}
    access_token = security_manager.create_access_token({"sub": str(user.id)}, extra_claims=extra_claims)

    return TokenResponse(access_token=access_token, refresh_token=refresh_token, expires_in=1800)
