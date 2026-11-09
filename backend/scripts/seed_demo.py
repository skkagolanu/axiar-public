"""Idempotent demo-tenant seed.

Run standalone (``python -m scripts.seed_demo``, e.g. on container boot when
``DEMO_SEED=true`` — see Dockerfile.edge) or via the reset endpoint
(``app/api/v1/endpoints/demo.py``), which wipes all non-tenant tables first and
then calls :func:`seed` to restore this exact pristine state.

Everything is keyed on natural keys (tenant slug, user emails, service names),
so running it any number of times changes nothing after the first. Credentials
below are deliberately public — they are shown on the demo login page.
"""

import asyncio
import datetime
import logging
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import security_manager
from app.domain.booking.models import Booking, BookingStatus, FieldAgent, Provider, Service
from app.domain.tenant.models import Tenant
from app.domain.user.models import User, UserRole

logger = logging.getLogger(__name__)

DEMO_PASSWORD = "AxiarDemo1"  # published on the login page — demo data only
DEMO_USERS = [
    ("provider@example.test", UserRole.PROVIDER, "Demi", "Owner"),
    ("customer@example.test", UserRole.CUSTOMER, "Casey", "Customer"),
    ("field-agent@example.test", UserRole.FIELD_AGENT, "Alex", "Agent"),
]
DEMO_SERVICES = [
    ("Deep Clean", "cleaning", 8500, 120),
    ("Window Cleaning", "cleaning", 4500, 60),
    ("Garden Tidy", "gardening", 6000, 90),
]


async def _get_or_create_tenant(session: AsyncSession) -> Tenant:
    tenant: Tenant | None = (
        await session.execute(select(Tenant).where(Tenant.slug == settings.DEMO_TENANT_SLUG))
    ).scalar_one_or_none()
    if not tenant:
        tenant = Tenant(name="Axiar Demo", slug=settings.DEMO_TENANT_SLUG, is_active=True, settings={"synthetic": True})
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
    return tenant


async def _get_or_create_user(
    session: AsyncSession,
    tenant_id: UUID,
    email: str,
    role: UserRole,
    first: str,
    last: str,
) -> User:
    user: User | None = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if not user:
        user = User(
            id=uuid4(),
            tenant_id=tenant_id,
            email=email,
            hashed_password=security_manager.hash_password(DEMO_PASSWORD),
            first_name=first,
            last_name=last,
            role=role,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    elif user.tenant_id != tenant_id:
        # Keep the synthetic demo accounts in the dedicated demo tenant.
        user.tenant_id = tenant_id
        await session.commit()
    return user


async def seed(session: AsyncSession) -> None:
    """Create tenant, users, provider, services, agent, and sample bookings."""
    tenant = await _get_or_create_tenant(session)
    users = {
        email: await _get_or_create_user(session, tenant.id, email, role, first, last)
        for email, role, first, last in DEMO_USERS
    }
    owner = users["provider@example.test"]
    customer = users["customer@example.test"]
    agent_user = users["field-agent@example.test"]

    provider = (await session.execute(select(Provider).where(Provider.user_id == owner.id))).scalar_one_or_none()
    if not provider:
        provider = Provider(id=uuid4(), tenant_id=tenant.id, user_id=owner.id, business_name="Sparkle Cleaning Co")
        session.add(provider)
        await session.commit()
        await session.refresh(provider)
    elif provider.tenant_id != tenant.id:
        provider.tenant_id = tenant.id
        await session.commit()

    services = {}
    for name, stype, price, minutes in DEMO_SERVICES:
        svc = (
            await session.execute(select(Service).where(Service.provider_id == provider.id, Service.name == name))
        ).scalar_one_or_none()
        if not svc:
            svc = Service(
                id=uuid4(),
                tenant_id=tenant.id,
                provider_id=provider.id,
                name=name,
                service_type=stype,
                base_price_cents=price,
                duration_minutes=minutes,
            )
            session.add(svc)
            await session.commit()
            await session.refresh(svc)
        elif svc.tenant_id != tenant.id:
            svc.tenant_id = tenant.id
            await session.commit()
        services[name] = svc

    agent = (await session.execute(select(FieldAgent).where(FieldAgent.user_id == agent_user.id))).scalar_one_or_none()
    if not agent:
        agent = FieldAgent(tenant_id=tenant.id, user_id=agent_user.id, provider_id=provider.id, is_active=True)
        session.add(agent)
        await session.commit()
    elif agent.tenant_id != tenant.id:
        agent.tenant_id = tenant.id
        await session.commit()

    # Sample bookings only when the demo customer has none (idempotence key).
    has_bookings = (
        await session.execute(select(Booking.id).where(Booking.customer_id == customer.id).limit(1))
    ).scalar_one_or_none()
    if has_bookings:
        existing_bookings = (await session.execute(select(Booking).where(Booking.customer_id == customer.id))).scalars().all()
        changed = False
        for booking in existing_bookings:
            if booking.tenant_id != tenant.id:
                booking.tenant_id = tenant.id
                changed = True
        if changed:
            await session.commit()
    if not has_bookings:
        now = datetime.datetime.now(datetime.timezone.utc)
        samples = [
            (services["Deep Clean"], now - datetime.timedelta(days=7), BookingStatus.COMPLETED),
            (services["Window Cleaning"], now + datetime.timedelta(days=2), BookingStatus.CONFIRMED),
            (services["Garden Tidy"], now + datetime.timedelta(days=5), BookingStatus.PENDING),
        ]
        for svc, when, status in samples:
            session.add(
                Booking(
                    tenant_id=tenant.id,
                    customer_id=customer.id,
                    provider_id=provider.id,
                    service_id=svc.id,
                    scheduled_time=when,
                    location_postcode="SW1A 1AA",
                    location_address="10 Demo Street, London",
                    base_price_cents=svc.base_price_cents,
                    duration_minutes=svc.duration_minutes,
                    status=status,
                )
            )
        await session.commit()

    logger.info("Demo seed complete (tenant=%s provider=%s)", tenant.id, provider.id)


async def _main() -> None:
    from app.core.database import db_manager

    async with db_manager.get_session() as session:
        await seed(session)
    for engine in db_manager.engines.values():
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main())
