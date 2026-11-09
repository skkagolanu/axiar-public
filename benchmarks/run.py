"""Real HTTP/DB/Kafka benchmark. Run with backend/.venv/bin/python; see --help."""

import argparse
import asyncio
import hashlib
import json
import logging
import math
import os
import platform
import shutil
import statistics
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from environment import API_URL, BROKER, DB_URL, NAMES, REDIS_URL, docker, environment

ROOT = Path(__file__).resolve().parents[1]
PARSER = argparse.ArgumentParser(description=__doc__)
PARSER.add_argument("--source", type=Path, default=ROOT)
PARSER.add_argument("--label", required=True)
PARSER.add_argument("--rows", type=int, default=100000)
PARSER.add_argument("--seconds", type=int, default=30)
PARSER.add_argument("--users", default="10,50,100")
PARSER.add_argument("--repeats", type=int, default=3)
PARSER.add_argument("--rounds", type=int, default=10)
PARSER.add_argument("--outage-seconds", type=int, default=10)
PARSER.add_argument("--only", choices=["all", "evidence", "api", "concurrency", "events", "database"], default="all")
PARSER.add_argument("--contention-users", default="10,50,100")
ARGS = PARSER.parse_args()
SOURCE = ARGS.source.resolve()
OUT = ROOT / "benchmarks" / "results" / ARGS.label
OUT.mkdir(parents=True, exist_ok=False)
SOURCE_ORIGIN = SOURCE
SOURCE = OUT / "source"
shutil.copytree(
    SOURCE_ORIGIN / "backend",
    SOURCE / "backend",
    ignore=shutil.ignore_patterns(
        ".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".hypothesis", ".env", ".env.*", ".coverage"
    ),
)
SOURCE_DIGEST = hashlib.sha256()
for source_file in sorted((SOURCE / "backend").rglob("*.py")):
    SOURCE_DIGEST.update(str(source_file.relative_to(SOURCE)).encode())
    SOURCE_DIGEST.update(source_file.read_bytes())
shutil.copy2(Path(__file__), OUT / "run.py")
shutil.copy2(ROOT / "benchmarks/environment.py", OUT / "environment.py")
os.environ.update(environment())
sys.path.insert(0, str(SOURCE / "backend"))

import asyncpg
import httpx
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from app.core.cache import cache_manager
from app.core.database import db_manager
from app.core.event_bus import event_bus
from app.core.security import security_manager
from app.core.tenant_context import set_current_tenant
from app.domain.booking.models import Booking, BookingStatus, Provider, Service
from app.domain.booking.repository import BookingRepository
from app.domain.tenant.models import Tenant
from app.domain.user.models import User, UserRole
from app.main import app  # imports the actual app and all mapped models
from redis.asyncio import Redis
from sqlalchemy import event, insert

logging.getLogger().setLevel(logging.ERROR)
ANCHOR = datetime(2100, 1, 1, tzinfo=timezone.utc)
HISTORY = datetime(2030, 1, 1, tzinfo=timezone.utc)


def uid(value):
    return uuid5(NAMESPACE_URL, f"axiar-benchmark-v1/{value}")


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, default=str) + "\n")


def distribution(values):
    if not values:
        return {"count": 0, "p50_ms": None, "p95_ms": None}
    ordered = sorted(values)
    return {
        "count": len(values),
        "p50_ms": ordered[math.ceil(len(values) * 0.5) - 1],
        "p95_ms": ordered[math.ceil(len(values) * 0.95) - 1],
        "mean_ms": statistics.mean(values),
    }


def identity(t, p, kind="customer"):
    tenant = uid(f"tenant/{t}")
    user = uid(f"{kind}/{t}/{p}")
    token = security_manager.create_access_token(
        {"sub": str(user)}, expires_delta=timedelta(hours=6), extra_claims={"tenant_id": str(tenant)}
    )
    return {"Authorization": f"Bearer {token}", "X-Tenant-ID": str(tenant)}


def payload(t, p, slot, description="benchmark-workflow"):
    return {
        "provider_id": str(uid(f"provider/{t}/{p}")),
        "service_id": str(uid(f"service/{t}/{p}")),
        "scheduled_time": slot.isoformat(),
        "duration_minutes": 60,
        "location_postcode": "NG7 2RD",
        "base_price_cents": 5000,
        "description": description,
    }


async def connection():
    conn = await asyncpg.connect(DB_URL.replace("postgresql+asyncpg", "postgresql"))
    if await conn.fetchval("select current_database()") != "axiar_benchmark":
        raise RuntimeError("Refusing to mutate a non-benchmark database")
    return conn


async def seed():
    conn = await connection()
    try:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public; CREATE EXTENSION postgis")
    finally:
        await conn.close()
    # Use the real migration chain, not an approximation of production tables.
    with (OUT / "migrations.log").open("w") as log:
        subprocess.run(
            [str(ROOT / "backend/.venv/bin/alembic"), "upgrade", "head"],
            cwd=SOURCE / "backend",
            env=environment(),
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
        )
    async with db_manager.get_session() as session:
        for t in range(2):
            session.add(Tenant(id=uid(f"tenant/{t}"), name=f"Benchmark {t}", slug=f"bench-{t}", is_active=True))
        await session.flush()
        for t in range(2):
            for p in range(21):
                for kind, role in [("customer", UserRole.CUSTOMER), ("provider-user", UserRole.PROVIDER)]:
                    session.add(
                        User(
                            id=uid(f"{kind}/{t}/{p}"),
                            tenant_id=uid(f"tenant/{t}"),
                            email=f"{kind}-{t}-{p}@benchmark.invalid",
                            first_name="Synthetic",
                            last_name=kind,
                            role=role,
                            is_active=True,
                            is_verified=True,
                        )
                    )
        await session.flush()
        for t in range(2):
            for p in range(21):
                session.add(
                    Provider(
                        id=uid(f"provider/{t}/{p}"),
                        tenant_id=uid(f"tenant/{t}"),
                        user_id=uid(f"provider-user/{t}/{p}"),
                        business_name=f"Synthetic {p}",
                    )
                )
        await session.flush()
        for t in range(2):
            for p in range(21):
                session.add(
                    Service(
                        id=uid(f"service/{t}/{p}"),
                        tenant_id=uid(f"tenant/{t}"),
                        provider_id=uid(f"provider/{t}/{p}"),
                        name="Synthetic cleaning",
                        service_type="cleaning",
                        base_price_cents=5000,
                        duration_minutes=60,
                    )
                )
        await session.flush()
        for start in range(0, ARGS.rows, 2000):
            rows = []
            for i in range(start, min(start + 2000, ARGS.rows)):
                t, p = i % 2, (i // 2) % 20
                rows.append(
                    dict(
                        id=uid(f"booking/{i}"),
                        tenant_id=uid(f"tenant/{t}"),
                        customer_id=uid(f"customer/{t}/{p}"),
                        provider_id=uid(f"provider/{t}/{p}"),
                        service_id=uid(f"service/{t}/{p}"),
                        scheduled_time=HISTORY + timedelta(hours=(i // 40) * 2),
                        duration_minutes=60,
                        status=BookingStatus.CONFIRMED,
                        location_postcode="NG7 2RD",
                        base_price_cents=5000,
                        description="benchmark-seed",
                    )
                )
            await session.execute(insert(Booking), rows)
    conn = await connection()
    await conn.execute("ANALYZE")
    count = await conn.fetchval("SELECT count(*) FROM bookings")
    await conn.close()
    assert count == ARGS.rows
    redis = Redis.from_url(REDIS_URL)
    await redis.flushdb()
    await redis.aclose()
    print(f"seeded {count} bookings", flush=True)


async def clean_workflows():
    conn = await connection()
    await conn.execute("DELETE FROM bookings WHERE description != 'benchmark-seed'; TRUNCATE outbox_messages")
    await conn.close()


async def wait_api(process):
    async with httpx.AsyncClient() as client:
        for _ in range(120):
            if process.poll() is not None:
                raise RuntimeError("API exited; inspect api.log")
            try:
                if (await client.get(API_URL + "/api/v1/health")).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.5)
    raise RuntimeError("API startup deadline exceeded")


async def start_api():
    env = environment()
    env["PYTHONPATH"] = str(SOURCE / "backend")
    log = (OUT / "api.log").open("a")
    process = subprocess.Popen(
        [
            str(ROOT / "backend/.venv/bin/python"),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "58089",
            "--workers",
            "1",
            "--no-access-log",
        ],
        cwd=SOURCE / "backend",
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    try:
        await wait_api(process)
    except BaseException:
        process.terminate()
        process.wait(timeout=15)
        log.close()
        raise
    return process, log


def stop_api(handle):
    process, log = handle
    process.terminate()
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    log.close()


async def api_benchmark():
    summaries = []
    for users in map(int, ARGS.users.split(",")):
        for repeat in range(ARGS.repeats):
            await clean_workflows()
            handle = await start_api()
            samples, journeys, failures, completed = [], [], [], []
            try:
                async with httpx.AsyncClient(
                    base_url=API_URL, timeout=60, limits=httpx.Limits(max_connections=users * 2)
                ) as client:

                    async def journey(vu, index, record):
                        t, p = vu % 2, (vu // 2) % 20
                        customer, provider = identity(t, p), identity(t, p, "provider-user")
                        slot = ANCHOR + timedelta(hours=(vu * 100000 + index) * 2)
                        begin = time.perf_counter()

                        async def call(method, path, expected, headers, **kwargs):
                            started = time.perf_counter()
                            try:
                                response = await client.request(method, path, headers=headers, **kwargs)
                                status = response.status_code
                            except httpx.HTTPError:
                                response, status = None, 0
                            elapsed = (time.perf_counter() - started) * 1000
                            if record:
                                samples.append(
                                    {
                                        "operation": method
                                        + " "
                                        + path.split("?")[0].replace(
                                            (
                                                str(response.json().get("id", ""))
                                                if response is not None and isinstance(response.json(), dict)
                                                else "__none__"
                                            ),
                                            "{id}",
                                        ),
                                        "ms": elapsed,
                                        "status": status,
                                        "expected": expected,
                                    }
                                )
                            if status != expected:
                                if record:
                                    failures.append(
                                        {
                                            "status": status,
                                            "body": response.text[:500] if response is not None else "network error",
                                        }
                                    )
                                raise RuntimeError("journey request failed")
                            return response

                        try:
                            await call("GET", "/api/v1/bookings/?limit=50", 200, provider)
                            created = await call("POST", "/api/v1/bookings/", 201, customer, json=payload(t, p, slot))
                            bid = created.json()["id"]
                            await call("PATCH", f"/api/v1/bookings/{bid}/status", 200, provider, json={"status": "confirmed"})
                            found = await call("GET", f"/api/v1/bookings/{bid}", 200, customer)
                            if found.json()["status"] != "confirmed":
                                raise AssertionError("read-after-confirm incorrect")
                            await call("PATCH", f"/api/v1/bookings/{bid}/status", 200, customer, json={"status": "cancelled"})
                            if record:
                                completed.append(bid)
                                journeys.append((time.perf_counter() - begin) * 1000)
                        except RuntimeError:
                            return

                    # Separate warm-up slots, outside the measured interval.
                    await asyncio.gather(*(journey(v, -1, False) for v in range(users)))
                    start = time.perf_counter()
                    deadline = start + ARGS.seconds

                    async def worker(vu):
                        i = 0
                        while time.perf_counter() < deadline:
                            await journey(vu, i, True)
                            i += 1

                    await asyncio.gather(*(worker(v) for v in range(users)))
                    elapsed = time.perf_counter() - start
                conn = await connection()
                actual = await conn.fetchval(
                    "SELECT count(*) FROM bookings WHERE id=ANY($1::uuid[]) AND status='CANCELLED'", completed
                )
                await conn.close()
                assert actual == len(completed), "completed journey DB invariant failed"
                errors = sum(s["status"] != s["expected"] for s in samples)
                summary = {
                    "users": users,
                    "repeat": repeat,
                    "elapsed_s": elapsed,
                    "requests_per_s": len(samples) / elapsed,
                    "successful_requests_per_s": (len(samples) - errors) / elapsed,
                    "workflows_per_s": len(completed) / elapsed,
                    "errors": errors,
                    "error_rate": errors / len(samples) if samples else None,
                    "requests": distribution([s["ms"] for s in samples]),
                    "journeys": distribution(journeys),
                    "persisted_cancelled_workflows": actual,
                    "failure_examples": failures[:5],
                }
                save(f"api-{users}-{repeat}-raw.json", {"samples": samples, "journey_ms": journeys})
                summaries.append(summary)
                save("api.json", summaries)
                print("api", json.dumps(summary), flush=True)
            finally:
                stop_api(handle)
    return summaries


async def concurrency_benchmark():
    await clean_workflows()
    handle = await start_api()
    rounds = []
    try:
        async with httpx.AsyncClient(base_url=API_URL, timeout=60, limits=httpx.Limits(max_connections=250)) as client:
            for n in map(int, ARGS.contention_users.split(",")):
                for r in range(ARGS.rounds):
                    slot = ANCHOR + timedelta(days=1000 + n * 20 + r)
                    # Populate the HTTP and DB pools before releasing simultaneous writes.
                    warmed = await asyncio.gather(
                        *(client.get("/api/v1/bookings/my-bookings", headers=identity(0, i % 20)) for i in range(n))
                    )
                    assert all(response.status_code == 200 for response in warmed)
                    barrier = asyncio.Event()

                    async def attempt(i):
                        await barrier.wait()
                        start = time.perf_counter()
                        try:
                            response = await client.post(
                                "/api/v1/bookings/",
                                headers=identity(0, i % 20),
                                json=payload(0, 20, slot, "benchmark-contention"),
                            )
                            status = response.status_code
                        except httpx.HTTPError:
                            status = 0
                        return {"status": status, "ms": (time.perf_counter() - start) * 1000}

                    tasks = [asyncio.create_task(attempt(i)) for i in range(n)]
                    barrier.set()
                    results = await asyncio.gather(*tasks)
                    conn = await connection()
                    count = await conn.fetchval(
                        "SELECT count(*) FROM bookings WHERE provider_id=$1 AND scheduled_time=$2", uid("provider/0/20"), slot
                    )
                    await conn.close()
                    item = {
                        "n": n,
                        "round": r,
                        "persisted": count,
                        "conflicting_pairs": count * (count - 1) // 2,
                        "statuses": dict(Counter(x["status"] for x in results)),
                        "latency": distribution([x["ms"] for x in results]),
                    }
                    rounds.append(item)
                    save("concurrency.json", rounds)
                    print("concurrency", json.dumps(item), flush=True)
            # Adjacent intervals and independent tenants must not be rejected by coarse locks.
            independent = []
            for t in range(2):
                for i in range(2):
                    response = await client.post(
                        "/api/v1/bookings/",
                        headers=identity(t, 0),
                        json=payload(t, 20, ANCHOR + timedelta(days=20000, hours=i)),
                    )
                    independent.append(response.status_code)
            save("concurrency-independent.json", independent)
            assert independent == [201] * 4
    finally:
        stop_api(handle)
    return rounds


async def database_benchmark():
    await clean_workflows()
    samples, statements = [], []
    engine = db_manager.engines["main"]

    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append((statement, parameters))

    set_current_tenant(uid("tenant/0"))
    for i in range(35):
        async with db_manager.session_makers["main"]() as session:
            if i == 0:
                event.listen(engine.sync_engine, "before_cursor_execute", capture)
            begin = time.perf_counter()
            available = await BookingRepository(session).check_availability(uid("provider/0/0"), ANCHOR, 60)
            elapsed = (time.perf_counter() - begin) * 1000
            if i == 0:
                event.remove(engine.sync_engine, "before_cursor_execute", capture)
            assert available
            await session.rollback()
            if i >= 5:
                samples.append(elapsed)
    plans = []
    for statement, params in statements:
        async with engine.connect() as conn:
            result = await conn.exec_driver_sql("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement, params)
            plans.append({"sql": statement, "parameters": params, "plan": result.scalar()})
            await conn.rollback()
    # Existing tenant cache: isolated Redis has no unrelated traffic during this component experiment.
    from app.core.tenant_middleware import TenantMiddleware

    await cache_manager.init()
    redis = Redis.from_url(REDIS_URL)
    middleware = TenantMiddleware(app)
    cache_samples = {"cold_ms": [], "warm_ms": []}
    for kind in cache_samples:
        for i in range(30):
            if kind == "cold_ms":
                await redis.delete("tenant:resolve:bench-0")
            start = time.perf_counter()
            resolved = await middleware._resolve("bench-0")
            assert resolved["id"] == str(uid("tenant/0"))
            cache_samples[kind].append((time.perf_counter() - start) * 1000)
    # Hit/miss counters only for exactly 100 scoped lookups after deliberate eviction.
    await redis.delete("tenant:resolve:bench-0")
    before = await redis.info("stats")
    for _ in range(100):
        await middleware._resolve("bench-0")
    after = await redis.info("stats")
    hits = after["keyspace_hits"] - before["keyspace_hits"]
    misses = after["keyspace_misses"] - before["keyspace_misses"]
    other = await middleware._resolve("bench-1")
    assert other["id"] == str(uid("tenant/1")) != resolved["id"]
    await redis.aclose()
    await cache_manager.close()
    result = {
        "availability": distribution(samples),
        "availability_raw_ms": samples,
        "plans": plans,
        "tenant_cache": {
            **{k: distribution(v) for k, v in cache_samples.items()},
            "raw": cache_samples,
            "hits": hits,
            "misses": misses,
            "hit_rate": hits / (hits + misses),
            "tenant_isolation": True,
        },
    }
    save("database.json", result)
    print(
        "database",
        json.dumps({"availability": result["availability"], "cache_hits": hits, "cache_misses": misses}),
        flush=True,
    )
    return result


async def events_benchmark():
    from app.consumers.outbox_relay import relay_once, relay_outbox

    await clean_workflows()
    await event_bus.start()
    assert event_bus.producer is not None
    # Ensure topic exists before subscribing, then establish an observation boundary.
    await event_bus.producer.send_and_wait("axiar.booking.events", {"probe": True})
    consumer = AIOKafkaConsumer(
        "axiar.booking.events",
        bootstrap_servers=BROKER,
        auto_offset_reset="latest",
        group_id=None,
        value_deserializer=lambda v: json.loads(v.decode()),
    )
    await consumer.start()
    await consumer.getmany(timeout_ms=1000)
    await consumer.seek_to_end()
    observed = []

    async def drain(seconds=2):
        deadline = time.perf_counter() + seconds
        while time.perf_counter() < deadline:
            batches = await consumer.getmany(timeout_ms=200)
            for batch in batches.values():
                observed.extend(record.value for record in batch)

    async def create_one(i, commit=True):
        set_current_tenant(uid("tenant/0"))
        async with db_manager.session_makers["main"]() as session:
            booking = await BookingRepository(session).create(
                customer_id=uid("customer/0/0"),
                provider_id=uid("provider/0/20"),
                service_id=uid("service/0/20"),
                scheduled_time=ANCHOR + timedelta(days=30000 + i),
                duration_minutes=60,
                location_postcode="NG7 2RD",
                base_price_cents=5000,
                description="benchmark-events",
            )
            bid = str(booking.id)
            if commit:
                await session.commit()
            else:
                await session.rollback()
            return bid

    healthy_ids = [await create_one(i) for i in range(10)]
    aborted = await create_one(10, False)
    await relay_once()
    await drain()
    healthy = [e for e in observed if e.get("aggregate_id") in healthy_ids]
    phantom = [e for e in observed if e.get("aggregate_id") == aborted]
    result = {
        "healthy": {
            "committed": 10,
            "delivered": len(healthy),
            "missing": len(set(healthy_ids) - {e["aggregate_id"] for e in healthy}),
            "semantic_duplicates": len(healthy) - len({e["aggregate_id"] for e in healthy}),
            "rolled_back_events": len(phantom),
        }
    }
    await consumer.stop()
    await event_bus.stop()
    event_bus.producer = None
    # Cold-start outage is distinct from an already-connected producer outage.
    docker("stop", "--time", "5", NAMES[2], stdout=subprocess.DEVNULL)
    try:
        await event_bus.start()
        assert event_bus.producer is None
        outage_started = time.perf_counter()
        outage_ids = [await create_one(100 + i) for i in range(20)]
        await relay_once()
        elapsed = time.perf_counter() - outage_started
        await asyncio.sleep(max(0, ARGS.outage_seconds - elapsed))
    finally:
        docker("start", NAMES[2], stdout=subprocess.DEVNULL)
    # Confirm broker readiness independently, without repairing the app's producer.
    probe = AIOKafkaProducer(bootstrap_servers=BROKER)
    for _ in range(60):
        try:
            await probe.start()
            break
        except Exception:
            await asyncio.sleep(0.5)
    else:
        raise RuntimeError("Kafka did not recover")
    await probe.stop()
    ready = time.perf_counter()
    consumer = AIOKafkaConsumer(
        "axiar.booking.events",
        bootstrap_servers=BROKER,
        auto_offset_reset="earliest",
        group_id=None,
        value_deserializer=lambda v: json.loads(v.decode()),
    )
    await consumer.start()
    task = asyncio.create_task(relay_outbox())
    observed = []
    recovery = None
    try:
        while time.perf_counter() - ready < 20:
            await drain(0.25)
            matching = [e for e in observed if e.get("aggregate_id") in outage_ids]
            if {e["aggregate_id"] for e in matching} == set(outage_ids):
                recovery = time.perf_counter() - ready
                await drain(1)
                break
        matching = [e for e in observed if e.get("aggregate_id") in outage_ids]
        conn = await connection()
        backlog = await conn.fetch("SELECT status, count(*) FROM outbox_messages GROUP BY status")
        await conn.close()
        result["cold_start_outage"] = {
            "outage_s": max(ARGS.outage_seconds, elapsed),
            "committed_during_outage": 20,
            "deadline_s": 20,
            "recovery_s": recovery,
            "delivered": len(matching),
            "missing": len(set(outage_ids) - {e["aggregate_id"] for e in matching}),
            "semantic_duplicates": len(matching) - len({e["aggregate_id"] for e in matching}),
            "outbox_status_counts": [dict(r) for r in backlog],
        }
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await consumer.stop()
        await event_bus.stop()
        event_bus.producer = None
    save(
        "events-ledger.json",
        {
            "healthy_ids": healthy_ids,
            "aborted_id": aborted,
            "healthy_events": healthy,
            "phantom_events": phantom,
            "outage_ids": outage_ids,
            "observed_after_recovery": observed,
        },
    )
    save("events.json", result)
    print("events", json.dumps(result), flush=True)
    return result


async def main():
    save(
        "manifest.json",
        {
            "label": ARGS.label,
            "source": str(SOURCE),
            "source_origin": str(SOURCE_ORIGIN),
            "frozen_source_sha256": SOURCE_DIGEST.hexdigest(),
            "baseline_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "arguments": vars(ARGS),
            "utc": datetime.now(timezone.utc),
            "python": sys.version,
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
            "workers": 1,
            "pool_size": 30,
            "max_overflow": 30,
            "rate_limit_enabled": False,
            "demo_mode": False,
            "anchor": ANCHOR,
            "seed_namespace": "axiar-benchmark-v1",
            "tenants": 2,
            "providers_per_tenant": 21,
            "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "images": json.loads(docker("inspect", *NAMES, capture_output=True, text=True).stdout),
            "dependencies": (
                subprocess.check_output([sys.executable, "-m", "pip", "freeze"], text=True)
                if subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True).returncode == 0
                else subprocess.check_output(["uv", "pip", "freeze", "--python", sys.executable], text=True)
            ),
        },
    )
    (OUT / "source.diff").write_text(
        subprocess.check_output(["git", "diff"], cwd=ROOT, text=True)
        if SOURCE_ORIGIN == ROOT
        else "Frozen source snapshot; see manifest frozen_source_sha256 and source_origin.\n"
    )
    await seed()
    summary = {}
    for name, function in [
        ("database", database_benchmark),
        ("api", api_benchmark),
        ("concurrency", concurrency_benchmark),
        ("events", events_benchmark),
    ]:
        if ARGS.only in ("all", name) or (ARGS.only == "evidence" and name != "api"):
            summary[name] = await function()
            save("summary.json", summary)
    for engine in set(db_manager.engines.values()):
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
