"""Real five-request booking workflows while the isolated Kafka broker is stopped.

Run after sustain.py qualification and BEFORE resetting its high fixture. Uses
only the application's own background relay/reconnect; never calls relay_once.
"""

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import asyncpg
import httpx
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition
from environment import API_URL, BROKER, DB_URL, NAMES, docker, environment

ROOT = Path(__file__).resolve().parents[1]
TOPIC = "axiar.booking.events"


def uid(value):
    return str(uuid5(NAMESPACE_URL, f"axiar-extremes-v1/{value}"))


async def main():
    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, asyncio.current_task().cancel)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--cold-start", action="store_true")
    parser.add_argument("--outage-seconds", type=int, default=10)
    parser.add_argument("--workflows", type=int, default=20)
    args = parser.parse_args()
    if args.workflows != 20 or args.outage_seconds < 10:
        parser.error("Use twenty complete workflows and at least ten seconds of outage")
    # A concurrent campaign must fail preflight before Kafka is touched.
    for port in [58089, *range(58100, 58112)]:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    label = docker(
        "inspect", "--format", '{{index .Config.Labels "axiar.benchmark"}}', NAMES[2], capture_output=True, text=True
    ).stdout.strip()
    assert label == "isolated"
    out = ROOT / "benchmarks/results" / args.label
    out.mkdir(parents=True, exist_ok=False)
    harness = out / "harness"
    harness.mkdir()
    for name in ("outage_workflows.py", "worker_server.py", "environment.py"):
        shutil.copy2(ROOT / "benchmarks" / name, harness / name)
    # Read the already frozen backend from the qualification experiment.
    source = args.source.resolve()
    assert (source / "backend/app/main.py").exists()
    digest = hashlib.sha256()
    for path in sorted((source / "backend").rglob("*.py")):
        digest.update(str(path.relative_to(source)).encode())
        digest.update(path.read_bytes())
    env = environment()
    env.update(PYTHONPATH=str(source / "backend"), DATABASE_POOL_SIZE="4", DATABASE_MAX_OVERFLOW="0")
    metrics = out / "metrics"
    metrics.mkdir()
    env["PROMETHEUS_MULTIPROC_DIR"] = str(metrics)
    os.environ.update(env)
    sys.path.insert(0, str(source / "backend"))
    from app.core.security import security_manager

    def headers(t, kind):
        token = security_manager.create_access_token(
            {"sub": uid(f"{kind}/{t}/0")},
            expires_delta=timedelta(hours=1),
            extra_claims={"tenant_id": uid(f"tenant/{t}")},
        )
        return {"Authorization": f"Bearer {token}", "X-Tenant-ID": uid(f"tenant/{t}")}

    def save(name, value):
        (out / name).write_text(json.dumps(value, indent=2, default=str) + "\n")

    conn = await asyncpg.connect(DB_URL.replace("postgresql+asyncpg", "postgresql"))
    assert await conn.fetchval("SELECT current_database()") == "axiar_benchmark"
    assert await conn.fetchval("SELECT count(*) FROM tenants") == 100
    assert await conn.fetchval("SELECT count(*) FROM bookings WHERE description='benchmark-seed'") == 100000
    initial = AIOKafkaConsumer(TOPIC, bootstrap_servers=BROKER, group_id=None, enable_auto_commit=False)
    await initial.start()
    try:
        partitions = [TopicPartition(TOPIC, p) for p in sorted(initial.partitions_for_topic(TOPIC) or [])]
        assert partitions
        offsets = await initial.end_offsets(partitions)
    finally:
        await initial.stop()
    save(
        "manifest.json",
        {
            "arguments": vars(args),
            "utc": datetime.now(timezone.utc),
            "source": source,
            "backend_sha256": digest.hexdigest(),
            "workers": 12,
            "pool": 4,
            "balancer": "least_conn",
            "offset_start": {str(p.partition): n for p, n in offsets.items()},
            "workflow": "schedule(limit=50), create, provider confirm, customer read, customer cancel",
            "recovery_boundary": "independent producer bootstrap succeeds to observing all expected Kafka event IDs",
            "fixture": "100 tenants / 100000 seeded bookings, plus the preceding qualification's cancelled bookings",
        },
    )
    api = None
    consumer = None
    broker_stopped = False
    samples, acknowledged, observed = [], {}, []
    try:
        with (out / "api.log").open("w") as log:
            if args.cold_start:
                docker("stop", "--time", "5", NAMES[2], stdout=subprocess.DEVNULL)
                broker_stopped = True
                outage_started = time.perf_counter()
            api = subprocess.Popen(
                [
                    sys.executable,
                    str(harness / "worker_server.py"),
                    "--workers",
                    "12",
                    "--policy",
                    "least_conn",
                    "--output",
                    str(out),
                ],
                cwd=source / "backend",
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            async with httpx.AsyncClient(base_url=API_URL, timeout=30) as client:
                for _ in range(120):
                    if api.poll() is not None:
                        raise RuntimeError("Application exited; inspect api.log")
                    try:
                        if (await client.get("/api/v1/health")).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(0.5)
                else:
                    raise RuntimeError("Application readiness deadline exceeded")
                if not args.cold_start:
                    docker("stop", "--time", "5", NAMES[2], stdout=subprocess.DEVNULL)
                    broker_stopped = True
                    outage_started = time.perf_counter()

                async def call(method, path, who, expected, **kwargs):
                    started = time.perf_counter()
                    response = await client.request(method, path, headers=who, **kwargs)
                    samples.append(
                        {
                            "method": method,
                            "path": path,
                            "status": response.status_code,
                            "elapsed_ms": (time.perf_counter() - started) * 1000,
                        }
                    )
                    save("http-samples.json", samples)
                    assert response.status_code == expected, response.text
                    return response.json()

                for number in range(args.workflows):
                    customer, provider = headers(number, "customer"), headers(number, "owner")
                    schedule = await call("GET", "/api/v1/bookings/?limit=50", provider, 200)
                    assert len(schedule) == 50
                    created = await call(
                        "POST",
                        "/api/v1/bookings/",
                        customer,
                        201,
                        json={
                            "provider_id": uid(f"provider/{number}/0"),
                            "service_id": uid(f"service/{number}/0"),
                            "scheduled_time": (
                                datetime(2105, 1, 1, tzinfo=timezone.utc)
                                + timedelta(days=int(args.cold_start), hours=number * 2)
                            ).isoformat(),
                            "duration_minutes": 60,
                            "base_price_cents": 5000,
                            "location_postcode": "NG7 2RD",
                            "description": "benchmark-outage-workflow",
                        },
                    )
                    path = f'/api/v1/bookings/{created["id"]}'
                    confirmed = await call("PATCH", path + "/status", provider, 200, json={"status": "confirmed"})
                    assert confirmed["status"] == "confirmed"
                    read = await call("GET", path, customer, 200)
                    assert read["status"] == "confirmed"
                    cancelled = await call("PATCH", path + "/status", customer, 200, json={"status": "cancelled"})
                    assert cancelled["status"] == "cancelled"
                    acknowledged[created["id"]] = uid(f"tenant/{number}")
                    save("acknowledged.json", acknowledged)
            ids = list(acknowledged)
            rows = await conn.fetch(
                "SELECT id,aggregate_id,tenant_id,event_type,status FROM outbox_messages "
                "WHERE aggregate_id=ANY($1::uuid[])",
                ids,
            )
            expected = {str(row["id"]): (str(row["aggregate_id"]), str(row["tenant_id"]), row["event_type"]) for row in rows}
            assert len(expected) == 60
            types = defaultdict(list)
            for aggregate, tenant, event_type in expected.values():
                assert acknowledged[aggregate] == tenant
                types[aggregate].append(event_type)
            assert len(types) == 20 and all(
                sorted(events) == ["booking.cancelled", "booking.confirmed", "booking.created"] for events in types.values()
            )
            assert all(row["status"] == "pending" for row in rows), "Broker is down; nothing can be broker-acknowledged"
            save("outbox-during-outage.json", [dict(row) for row in rows])
            await asyncio.sleep(max(0, args.outage_seconds - (time.perf_counter() - outage_started)))
            outage_seconds = time.perf_counter() - outage_started
            docker("start", NAMES[2], stdout=subprocess.DEVNULL)
            broker_stopped = False
            for _ in range(120):
                probe = AIOKafkaProducer(bootstrap_servers=BROKER)
                try:
                    await probe.start()
                    break
                except Exception:
                    await asyncio.sleep(0.5)
                finally:
                    await probe.stop()
            else:
                raise RuntimeError("Broker did not recover")
            broker_ready = time.perf_counter()
            consumer = AIOKafkaConsumer(TOPIC, bootstrap_servers=BROKER, group_id=None, enable_auto_commit=False)
            await consumer.start()
            consumer.unsubscribe()
            consumer.assign(partitions)
            for partition, offset in offsets.items():
                consumer.seek(partition, offset)
            counts = Counter()
            recovery = None
            deadline = broker_ready + 60
            # Continue observing for two seconds after complete recovery to detect duplicates.
            while time.perf_counter() < deadline:
                batches = await consumer.getmany(timeout_ms=200, max_records=5000)
                for batch in batches.values():
                    for record in batch:
                        event = json.loads(record.value)
                        if str(event.get("aggregate_id")) not in acknowledged:
                            continue
                        observed.append({"partition": record.partition, "offset": record.offset, "payload": event})
                        counts[str(event.get("event_id"))] += 1
                if recovery is None and set(expected) <= set(counts):
                    recovery = time.perf_counter() - broker_ready
                    deadline = time.perf_counter() + 2
            save("kafka-ledger.json", observed)
            durable = await conn.fetch("SELECT id,tenant_id,status FROM bookings WHERE id=ANY($1::uuid[])", ids)
            audits = await conn.fetch(
                "SELECT entity_id,tenant_id,count(*) n FROM audit_logs "
                "WHERE entity_type='booking' AND entity_id=ANY($1::uuid[]) GROUP BY entity_id,tenant_id",
                ids,
            )
            final = await conn.fetch("SELECT id,status FROM outbox_messages WHERE id=ANY($1::uuid[])", list(expected))
            mismatches = sum(
                expected.get(str(item["payload"].get("event_id")))
                != (
                    str(item["payload"].get("aggregate_id")),
                    str(item["payload"].get("tenant_id")),
                    item["payload"].get("event_type"),
                )
                for item in observed
            )
            result = {
                "completed_workflows_during_outage": len(acknowledged),
                "http_requests": len(samples),
                "outage_seconds": outage_seconds,
                "recovery_seconds_from_broker_ready": recovery,
                "expected_events": len(expected),
                "observed_expected_events": len(set(counts) & set(expected)),
                "missing_event_ids": sorted(set(expected) - set(counts)),
                "duplicate_deliveries": sum(max(0, counts[eid] - 1) for eid in expected),
                "payload_or_tenant_mismatches": mismatches,
                "durable_cancelled_in_owning_tenant": sum(
                    row["status"] == "CANCELLED" and str(row["tenant_id"]) == acknowledged[str(row["id"])] for row in durable
                ),
                "bookings_with_three_audits_in_owning_tenant": sum(
                    row["n"] == 3 and str(row["tenant_id"]) == acknowledged[str(row["entity_id"])] for row in audits
                ),
                "broker_acknowledged_outbox_rows": sum(row["status"] == "published" for row in final),
                "scope": "Observed Kafka deliveries, not exactly-once downstream effects; "
                "two-second duplicate observation tail",
            }
            save("result.json", result)
            print(json.dumps(result), flush=True)
            assert result["durable_cancelled_in_owning_tenant"] == result["bookings_with_three_audits_in_owning_tenant"] == 20
            assert result["broker_acknowledged_outbox_rows"] == result["observed_expected_events"] == 60
            assert not result["missing_event_ids"] and not mismatches and recovery is not None
    finally:
        if broker_stopped:
            docker("start", NAMES[2], stdout=subprocess.DEVNULL)
        if consumer:
            await consumer.stop()
        if api and api.poll() is None:
            os.killpg(api.pid, signal.SIGTERM)
            try:
                await asyncio.to_thread(api.wait, timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(api.pid, signal.SIGKILL)
                await asyncio.to_thread(api.wait)
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
