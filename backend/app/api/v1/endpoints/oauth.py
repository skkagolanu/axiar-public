from typing import Dict

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.config import settings
from app.core.database import get_db_session
from app.core.security import security_manager
from app.core.tenant_context import get_current_tenant
from app.domain.tenant.models import Tenant
from app.domain.user.models import User, UserRole
from app.domain.user.schemas import TokenResponse

router = APIRouter()


def _require_oauth(provider: str) -> None:
    credentials = {
        "google": (settings.GOOGLE_CLIENT_ID, settings.GOOGLE_CLIENT_SECRET),
        "microsoft": (settings.MICROSOFT_CLIENT_ID, settings.MICROSOFT_CLIENT_SECRET),
    }
    if settings.DEMO_MODE or not all(credentials[provider]):
        raise HTTPException(status_code=404, detail="Not found")


oauth = OAuth()
oauth.register(
    name="google",
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

oauth.register(
    name="microsoft",
    client_id=settings.MICROSOFT_CLIENT_ID,
    client_secret=settings.MICROSOFT_CLIENT_SECRET,
    server_metadata_url="https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


@router.get("/google", response_class=RedirectResponse)
async def google_login(request: Request):
    """Initiate Google OAuth login"""
    _require_oauth("google")
    redirect_uri = request.url_for("google_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


async def _get_or_create_oauth_user(db: AsyncSession, user_info: dict, provider: str) -> User:
    """Resolve an existing user by email or create one bound to the current tenant.

    The tenant is resolved from the request context (``X-Tenant-ID`` / ``X-Tenant-Slug``),
    falling back to the default tenant so OAuth-created users are never left without a
    ``tenant_id``. Existing users must belong to the same tenant or sign-in is rejected.
    """
    email = user_info.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Email not provided by OAuth provider")

    # Resolve the authoritative tenant for this OAuth callback.
    current_tenant_id = get_current_tenant()
    if current_tenant_id:
        tenant_result = await db.execute(select(Tenant).where(Tenant.id == current_tenant_id))
        tenant = tenant_result.scalar_one_or_none()
    else:
        tenant = None

    if not tenant:
        tenant_result = await db.execute(select(Tenant).where(Tenant.slug == "default"))
        tenant = tenant_result.scalar_one_or_none()
        if not tenant:
            raise HTTPException(status_code=500, detail="Default tenant not found")

    # Email lookup is cross-tenant for login; tenant is enforced after lookup.
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user:
        if user.tenant_id != tenant.id:
            raise HTTPException(status_code=403, detail="Account belongs to a different tenant")
        return user

    user = User(
        tenant_id=tenant.id,
        email=email,
        first_name=user_info.get("given_name", ""),
        last_name=user_info.get("family_name", ""),
        role=UserRole.CUSTOMER,
        is_active=True,
        is_verified=True,
        oauth_provider=provider,
        oauth_id=user_info.get("sub"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/google/callback", response_model=TokenResponse)
async def google_callback(request: Request, db: AsyncSession = Depends(get_db_session)):
    """Handle Google OAuth callback"""
    _require_oauth("google")
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get("userinfo")

    user = await _get_or_create_oauth_user(db, user_info, "google")

    access_token = security_manager.create_access_token({"sub": str(user.id)}, extra_claims={"tenant_id": str(user.tenant_id)})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/microsoft", response_class=RedirectResponse)
async def microsoft_login(request: Request):
    """Initiate Microsoft OAuth login"""
    _require_oauth("microsoft")
    redirect_uri = request.url_for("microsoft_callback")
    return await oauth.microsoft.authorize_redirect(request, redirect_uri)


@router.get("/microsoft/callback", response_model=TokenResponse)
async def microsoft_callback(request: Request, db: AsyncSession = Depends(get_db_session)):
    """Handle Microsoft OAuth callback"""
    _require_oauth("microsoft")
    token = await oauth.microsoft.authorize_access_token(request)
    user_info = token.get("userinfo")

    user = await _get_or_create_oauth_user(db, user_info, "microsoft")

    access_token = security_manager.create_access_token({"sub": str(user.id)}, extra_claims={"tenant_id": str(user.tenant_id)})
    return {"access_token": access_token, "token_type": "bearer"}
