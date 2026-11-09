"""Deterministic multi-tenant fixtures for the two sustained-load extremes."""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import asyncpg
from environment import DB_URL, REDIS_URL, environment
from redis.asyncio import Redis
from sqlalchemy import insert

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--source", type=Path, required=True)
parser.add_argument("--tenants", type=int, required=True)
parser.add_argument("--rows", type=int, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
os.environ.update(environment())
sys.path.insert(0, str(args.source.resolve() / "backend"))

from app.core.database import db_manager
from app.core.security import security_manager
from app.domain.booking.models import Booking, BookingStatus, Provider, Service
from app.domain.tenant.models import Tenant
from app.domain.user.models import User, UserRole
from app.main import app  # register mapped models


def uid(value):
    return uuid5(NAMESPACE_URL, f"axiar-extremes-v1/{value}")


def headers(t, p, kind):
    token = security_manager.create_access_token(
        {"sub": str(uid(f"{kind}/{t}/{p}"))},
        expires_delta=timedelta(hours=6),
        extra_claims={"tenant_id": str(uid(f"tenant/{t}"))},
    )
    return {"Authorization": f"Bearer {token}", "X-Tenant-ID": str(uid(f"tenant/{t}"))}


async def main():
    assert (args.tenants, args.rows) in [(10, 10000), (100, 100000)], "Only the two agreed dataset extremes are supported"
    conn = await asyncpg.connect(DB_URL.replace("postgresql+asyncpg", "postgresql"))
    assert await conn.fetchval("SELECT current_database()") == "axiar_benchmark"
    await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public; CREATE EXTENSION postgis")
    await conn.close()
    with args.output.with_suffix(".migrations.log").open("w") as log:
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=args.source / "backend",
            env=environment(),
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
        )
    async with db_manager.get_session() as session:
        session.add_all(
            [
                Tenant(id=uid(f"tenant/{t}"), name=f"Synthetic {t}", slug=f"extreme-{t}", is_active=True)
                for t in range(args.tenants)
            ]
        )
        await session.flush()
        for t in range(args.tenants):
            for p in range(10):
                for kind, role in [("customer", UserRole.CUSTOMER), ("owner", UserRole.PROVIDER)]:
                    session.add(
                        User(
                            id=uid(f"{kind}/{t}/{p}"),
                            tenant_id=uid(f"tenant/{t}"),
                            email=f"{kind}-{t}-{p}@extremes.invalid",
                            first_name="Synthetic",
                            last_name=kind,
                            role=role,
                            is_active=True,
                            is_verified=True,
                        )
                    )
        await session.flush()
        for t in range(args.tenants):
            session.add_all(
                [
                    Provider(
                        id=uid(f"provider/{t}/{p}"),
                        tenant_id=uid(f"tenant/{t}"),
                        user_id=uid(f"owner/{t}/{p}"),
                        business_name=f"Synthetic {p}",
                    )
                    for p in range(10)
                ]
            )
        await session.flush()
        for t in range(args.tenants):
            session.add_all(
                [
                    Service(
                        id=uid(f"service/{t}/{p}"),
                        tenant_id=uid(f"tenant/{t}"),
                        provider_id=uid(f"provider/{t}/{p}"),
                        name="Cleaning",
                        service_type="cleaning",
                        base_price_cents=5000,
                        duration_minutes=60,
                    )
                    for p in range(10)
                ]
            )
        await session.flush()
        for start in range(0, args.rows, 2000):
            rows = []
            for i in range(start, min(args.rows, start + 2000)):
                t = i % args.tenants
                p = (i // args.tenants) % 10
                ordinal = i // (args.tenants * 10)
                active = ordinal % 5 == 0
                anchor = datetime(2027 if active else 2025, 1, 1, tzinfo=timezone.utc)
                rows.append(
                    dict(
                        id=uid(f"booking/{i}"),
                        tenant_id=uid(f"tenant/{t}"),
                        customer_id=uid(f"customer/{t}/{p}"),
                        provider_id=uid(f"provider/{t}/{p}"),
                        service_id=uid(f"service/{t}/{p}"),
                        scheduled_time=anchor + timedelta(days=ordinal),
                        duration_minutes=60,
                        status=BookingStatus.CONFIRMED if active else BookingStatus.COMPLETED,
                        location_postcode="NG7 2RD",
                        base_price_cents=5000,
                        description="benchmark-seed",
                    )
                )
            await session.execute(insert(Booking), rows)
    conn = await asyncpg.connect(DB_URL.replace("postgresql+asyncpg", "postgresql"))
    await conn.execute("ANALYZE")
    count = await conn.fetchval("SELECT count(*) FROM bookings")
    assert count == args.rows
    await conn.close()
    cache = Redis.from_url(REDIS_URL)
    await cache.flushdb()
    await cache.aclose()
    # Interleave tenants so every initial VU uses a distinct tenant/provider pair.
    fixtures = [
        {
            "tenant_id": str(uid(f"tenant/{t}")),
            "provider_id": str(uid(f"provider/{t}/{p}")),
            "service_id": str(uid(f"service/{t}/{p}")),
            "customer_headers": headers(t, p, "customer"),
            "provider_headers": headers(t, p, "owner"),
        }
        for p in range(10)
        for t in range(args.tenants)
    ]
    args.output.write_text(json.dumps(fixtures))
    args.output.chmod(0o600)
    for engine in set(db_manager.engines.values()):
        await engine.dispose()
    print(f"Seeded {count} bookings across {args.tenants} tenants; 80% completed, 20% confirmed", flush=True)


asyncio.run(main())
