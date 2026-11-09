"""Measure the repository race using independent preconnected PostgreSQL transactions.

Run after run.py has seeded the benchmark database and stopped its API.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from environment import environment

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--source", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--rounds", type=int, default=10)
parser.add_argument("--concurrency", type=int, default=20)
args = parser.parse_args()
os.environ.update(environment())
sys.path.insert(0, str(args.source.resolve() / "backend"))

from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.database import db_manager
from app.core.exceptions import BookingConflictError
from app.core.tenant_context import set_current_tenant
from app.domain.booking.models import Booking
from app.domain.booking.repository import BookingRepository
from app.main import app  # register all SQLAlchemy models


def uid(value):
    return uuid5(NAMESPACE_URL, f"axiar-benchmark-v1/{value}")


async def main():
    results = []
    for round_number in range(args.rounds):
        async with db_manager.get_session() as session:
            assert await session.scalar(text("SELECT current_database()")) == "axiar_benchmark"
            # The dedicated empty provider is reset before every round; no source changes or mocked barriers inside create().
            await session.execute(Booking.__table__.delete().where(Booking.provider_id == uid("provider/0/20")))
        barrier, ready = asyncio.Event(), 0
        slot = datetime(2100, 1, 1, tzinfo=timezone.utc) + timedelta(days=round_number)

        async def attempt():
            nonlocal ready
            set_current_tenant(uid("tenant/0"))
            try:
                async with db_manager.get_session() as session:
                    await session.execute(text("SELECT 1"))
                    ready += 1
                    if ready == args.concurrency:
                        barrier.set()
                    await barrier.wait()
                    await BookingRepository(session).create(
                        customer_id=uid("customer/0/0"),
                        provider_id=uid("provider/0/20"),
                        service_id=uid("service/0/20"),
                        scheduled_time=slot,
                        duration_minutes=60,
                        location_postcode="NG7 2RD",
                        base_price_cents=5000,
                        description="benchmark-transaction-contention",
                    )
                return "created"
            except BookingConflictError:
                return "conflict"
            except IntegrityError:
                return "constraint_conflict"
            except DBAPIError as exc:
                return f"transaction_failure:{getattr(exc.orig, 'sqlstate', 'unknown')}"
            finally:
                set_current_tenant(None)

        start = time.perf_counter()
        outcomes = await asyncio.wait_for(asyncio.gather(*(attempt() for _ in range(args.concurrency))), timeout=60)
        async with db_manager.get_session() as session:
            count = await session.scalar(
                select(func.count()).select_from(Booking).where(Booking.provider_id == uid("provider/0/20"))
            )
        results.append(
            {
                "round": round_number,
                "simultaneous_transactions": args.concurrency,
                "outcomes": dict(Counter(outcomes)),
                "persisted": count,
                "conflicting_pairs": count * (count - 1) // 2,
                "elapsed_s": time.perf_counter() - start,
            }
        )
        args.output.write_text(json.dumps(results, indent=2) + "\n")
        print(json.dumps(results[-1]), flush=True)
    for engine in set(db_manager.engines.values()):
        await engine.dispose()


asyncio.run(main())
