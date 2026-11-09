"""A single auditable, contiguous-workflow experiment with bounded worker pools."""

import argparse
import asyncio
import glob
import gzip
import hashlib
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import asyncpg
import httpx
from environment import API_URL, DB_URL, NAMES, docker, environment
from prometheus_client import CollectorRegistry, generate_latest, multiprocess
from prometheus_client.mmap_dict import MmapedDict
from prometheus_client.parser import text_string_to_metric_families

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--label", required=True)
parser.add_argument("--source", type=Path, default=ROOT)
parser.add_argument("--workers", type=int, default=4)
parser.add_argument("--pool", type=int, default=12)
parser.add_argument("--balancer", choices=("shared_socket", "least_conn", "round_robin"), default="shared_socket")
parser.add_argument("--db-cpus", type=int, default=2)
parser.add_argument("--db-memory-mib", type=int, default=1024)
parser.add_argument("--kafka-memory-mib", type=int, default=1024)
parser.add_argument(
    "--shared-buffers-mib",
    type=int,
    default=128,
    help="Postgres cache; only the isolated benchmark DB restarts before seeding",
)
parser.add_argument("--rate", type=int, default=100, help="offered COMPLETE workflows per second")
parser.add_argument("--duration", default="30s")
parser.add_argument("--vus", type=int, default=500)
parser.add_argument("--tenants", type=int, default=100)
parser.add_argument("--rows", type=int, default=100000)
parser.add_argument(
    "--live-status", action="store_true", help="Read local k6 counters every ten seconds; same setting for comparisons"
)
parser.add_argument(
    "--native-profile", action="store_true", help="Diagnostic native/Python stacks; excluded from performance claims"
)
parser.add_argument(
    "--sample",
    action="store_true",
    help="Diagnostic sampling; not a final latency measurement",
)
parser.add_argument(
    "--cprofile",
    action="store_true",
    help="Diagnostic deterministic profile; one worker only",
)
args = parser.parse_args()
if args.native_profile:
    args.sample = True
if (args.tenants, args.rows) not in ((10, 10000), (100, 100000)):
    parser.error("Use the agreed extremes: 10 tenants/10,000 bookings or 100 tenants/100,000 bookings")
OUT = ROOT / "benchmarks/results" / args.label
OUT.mkdir(parents=True, exist_ok=False)
HARNESS = OUT / "harness"
HARNESS.mkdir()
for filename in [
    "environment.py",
    "fixture.py",
    "workflows.js",
    "sustain.py",
    "cpu_server.py",
    "worker_server.py",
]:
    shutil.copy2(ROOT / "benchmarks" / filename, HARNESS / filename)
SOURCE = args.source.resolve()
source_origin = SOURCE
SOURCE = OUT / "source"
shutil.copytree(
    source_origin / "backend",
    SOURCE / "backend",
    ignore=shutil.ignore_patterns(
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".hypothesis",
        ".env",
        ".env.*",
        ".coverage",
    ),
)
source_digest = hashlib.sha256()
for source_file in sorted((SOURCE / "backend").rglob("*.py")):
    source_digest.update(str(source_file.relative_to(SOURCE)).encode())
    source_digest.update(source_file.read_bytes())


def save(name, data):
    (OUT / name).write_text(json.dumps(data, indent=2, default=str) + "\n")


def collect_metrics(path):
    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry, path=str(path))
    return generate_latest(registry)


def response_count(payload):
    return sum(
        sample.value
        for family in text_string_to_metric_families(payload.decode())
        for sample in family.samples
        if sample.name == "http_requests_total"
    )


def worker_snapshot(path):
    result = {}
    for counter in path.glob("counter_*.db"):
        pid = int(counter.stem.split("_")[-1])
        count = sum(
            value
            for key, value, _, _ in MmapedDict.read_all_values_from_file(str(counter))
            if json.loads(key)[1] == "http_requests_total"
        )
        stat = Path(f"/proc/{pid}/stat").read_text().split()
        result[str(pid)] = {
            "responses": count,
            "cpu_s": (int(stat[13]) + int(stat[14])) / os.sysconf("SC_CLK_TCK"),
            "nice": int(stat[18]),
            "affinity": sorted(os.sched_getaffinity(pid)),
        }
    return result


def processes(parent):
    found = {parent}
    for _ in range(4):
        for path in Path("/proc").glob("[0-9]*/stat"):
            try:
                data = path.read_text().split()
                if int(data[3]) in found:
                    found.add(int(data[0]))
            except (OSError, ValueError, IndexError):
                pass
    values = []
    for pid in sorted(found):
        try:
            stat = Path(f"/proc/{pid}/stat").read_text().split()
            values.append(
                {
                    "pid": pid,
                    "cpu_s": (int(stat[13]) + int(stat[14])) / os.sysconf("SC_CLK_TCK"),
                    "rss_kib": int(stat[23]) * os.sysconf("SC_PAGE_SIZE") // 1024,
                }
            )
        except OSError:
            pass
    return values


def host_snapshot():
    paths = {
        "cpu": "/proc/stat",
        "memory": "/proc/meminfo",
        "load": "/proc/loadavg",
        "cpu_pressure": "/proc/pressure/cpu",
        "memory_pressure": "/proc/pressure/memory",
        "io_pressure": "/proc/pressure/io",
        "vm": "/proc/vmstat",
    }
    result = {name: Path(path).read_text() for name, path in paths.items() if Path(path).exists()}
    for group, pattern in {
        "frequency": "/sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_cur_freq",
        "governor": "/sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_governor",
        "energy_preference": "/sys/devices/system/cpu/cpu[0-9]*/cpufreq/energy_performance_preference",
        "temperatures": "/sys/class/thermal/thermal_zone*/temp",
        "sensor_temperatures": "/sys/class/hwmon/hwmon*/temp*_input",
        "power": "/sys/class/power_supply/*/online",
    }.items():
        result[group] = {}
        for filename in glob.glob(pattern):
            try:
                result[group][filename] = Path(filename).read_text().strip()
            except OSError:
                pass
    return result


def container_cgroups(names=NAMES):
    groups = {}
    for name in names:
        pid = docker(
            "inspect",
            "--format",
            "{{.State.Pid}}",
            name,
            capture_output=True,
            text=True,
        ).stdout.strip()
        for line in Path(f"/proc/{pid}/cgroup").read_text().splitlines():
            if line.startswith("0::"):
                groups[name] = Path("/sys/fs/cgroup") / line.split("::", 1)[1].lstrip("/")
    return groups


LOAD_PID = None


async def live_status():
    started = time.perf_counter()
    async with httpx.AsyncClient(base_url="http://127.0.0.1:56565", timeout=2) as client:
        while True:
            await asyncio.sleep(10)
            try:
                response = await client.get("/v1/metrics")
                response.raise_for_status()
                metrics = {entry["id"]: entry["attributes"]["sample"] for entry in response.json()["data"]}
                progress = {
                    "phase": "load",
                    "elapsed_seconds": round(time.perf_counter() - started, 1),
                    "successful_workflows": metrics.get("completed_workflows", {}).get("count"),
                    "completed_workflows_per_second": metrics.get("completed_workflows", {}).get("rate"),
                    "workflow_error_rate": metrics.get("workflow_errors", {}).get("rate"),
                    "dropped_arrivals": metrics.get("dropped_iterations", {}).get("count", 0),
                    "http_requests": metrics.get("http_reqs", {}).get("count"),
                    "workflow_p95_ms": metrics.get("workflow_duration_ms", {}).get("p(95)"),
                    "workflow_p99_ms": metrics.get("workflow_duration_ms", {}).get("p(99)"),
                }
                save("live-progress.json", progress)
                print(json.dumps(progress), flush=True)
            except httpx.HTTPError:
                # Startup/shutdown can race this read-only status request.
                continue


async def monitor(parent, groups):
    with (OUT / "resources.ndjson").open("w") as output:
        while True:
            sample = {
                "utc": datetime.now(timezone.utc).isoformat(),
                "processes": processes(parent),
            }
            sample["host"] = host_snapshot()
            sample["load_generator"] = processes(LOAD_PID) if LOAD_PID else []
            sample["containers"] = {
                name: {
                    field: (path / field).read_text().strip()
                    for field in (
                        "cpu.stat",
                        "memory.current",
                        "memory.peak",
                        "memory.events",
                        "memory.pressure",
                        "io.stat",
                    )
                    if (path / field).exists()
                }
                for name, path in groups.items()
            }
            conn = await asyncpg.connect(DB_URL.replace("postgresql+asyncpg", "postgresql"))
            try:
                sample["db_activity"] = [dict(row) for row in await conn.fetch("""
                    SELECT state,wait_event_type,count(*) FROM pg_stat_activity
                    WHERE datname=current_database() GROUP BY state,wait_event_type
                """)]
                sample["db_stats"] = dict(await conn.fetchrow("""
                    SELECT xact_commit,xact_rollback,blks_hit,blks_read,deadlocks
                    FROM pg_stat_database WHERE datname=current_database()
                """))
            finally:
                await conn.close()
            output.write(json.dumps(sample) + "\n")
            output.flush()
            await asyncio.sleep(2)


async def main():
    global LOAD_PID
    if args.workers * args.pool > 80:
        raise ValueError("Total application connection budget must leave headroom under PostgreSQL max_connections=100")
    label = docker(
        "inspect",
        "--format",
        '{{index .Config.Labels "axiar.benchmark"}}',
        NAMES[0],
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert label == "isolated"
    docker("update", "--cpus", str(args.db_cpus), NAMES[0], stdout=subprocess.DEVNULL)
    for name, memory in ((NAMES[0], args.db_memory_mib), (NAMES[2], args.kafka_memory_mib)):
        if memory < 1024:
            raise ValueError("Use at least 1024 MiB for Postgres and Kafka")
        docker("update", f"--memory={memory}m", f"--memory-swap={memory*2}m", name, stdout=subprocess.DEVNULL)
    if not 64 <= args.shared_buffers_mib <= args.db_memory_mib // 2:
        raise ValueError("Shared buffers must be >=64 MiB and leave half the DB memory budget as headroom")
    current_buffers = int(
        docker(
            "exec",
            NAMES[0],
            "psql",
            "-U",
            "axiar",
            "-d",
            "axiar_benchmark",
            "-Atc",
            "SELECT pg_size_bytes(current_setting('shared_buffers'))",
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    if current_buffers != args.shared_buffers_mib * 2**20:
        docker(
            "exec",
            NAMES[0],
            "psql",
            "-U",
            "axiar",
            "-d",
            "axiar_benchmark",
            "-c",
            f"ALTER SYSTEM SET shared_buffers = '{args.shared_buffers_mib}MB'",
            stdout=subprocess.DEVNULL,
        )
        docker("restart", NAMES[0], stdout=subprocess.DEVNULL)
        for _ in range(120):
            ready = subprocess.run(
                [
                    *os.environ.get("BENCH_DOCKER_PREFIX", "sudo -n").split(),
                    "docker",
                    "exec",
                    NAMES[0],
                    "pg_isready",
                    "-U",
                    "axiar",
                    "-d",
                    "axiar_benchmark",
                ],
                capture_output=True,
            )
            if ready.returncode == 0:
                break
            await asyncio.sleep(0.5)
        else:
            raise RuntimeError("Benchmark PostgreSQL did not restart")
    env = environment()
    env.update(DATABASE_POOL_SIZE=str(args.pool), DATABASE_MAX_OVERFLOW="0")
    shutil.copy2(ROOT / "benchmarks/workflows.js", OUT / "workflows.js")
    with (OUT / "seed.log").open("w") as log:
        subprocess.run(
            [
                sys.executable,
                str(HARNESS / "fixture.py"),
                "--source",
                str(SOURCE),
                "--tenants",
                str(args.tenants),
                "--rows",
                str(args.rows),
                "--output",
                str(OUT / "identities.json"),
            ],
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
        )
    metric_dir = OUT / "metrics"
    metric_dir.mkdir()
    conn = await asyncpg.connect(DB_URL.replace("postgresql+asyncpg", "postgresql"))
    await conn.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
    durability = [
        dict(row)
        for row in await conn.fetch(
            "SELECT name,setting FROM pg_settings WHERE name=ANY($1::text[])",
            [
                "fsync",
                "synchronous_commit",
                "full_page_writes",
                "max_connections",
                "shared_buffers",
                "shared_preload_libraries",
                "track_io_timing",
                "track_wal_io_timing",
            ],
        )
    ]
    save("durability.json", durability)
    await conn.close()
    env.update(
        PYTHONPATH=str(SOURCE / "backend"),
        PROMETHEUS_MULTIPROC_DIR=str(metric_dir),
        WORKFLOWS_PER_SECOND=str(args.rate),
        DURATION=args.duration,
        VUS=str(args.vus),
        FIXTURE_PATH=str(OUT / "identities.json"),
        SUMMARY_PATH=str(OUT / "k6-summary.json"),
        API_URL=API_URL,
        K6_NO_USAGE_REPORT="true",
    )
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "58089",
        "--workers",
        str(args.workers),
        "--no-access-log",
    ]
    if args.balancer != "shared_socket":
        if args.sample or args.cprofile:
            raise ValueError("Use shared_socket for profiler diagnostics")
        command = [
            sys.executable,
            str(HARNESS / "worker_server.py"),
            "--workers",
            str(args.workers),
            "--policy",
            args.balancer,
            "--output",
            str(OUT),
        ]
    if args.cprofile:
        assert args.workers == 1
        env["AXIAR_PROFILE_PATH"] = str(OUT / "cpu.pstats")
        shutil.copy2(ROOT / "benchmarks/cpu_server.py", OUT / "cpu_server.py")
        command = [sys.executable, str(OUT / "cpu_server.py")]
    save(
        "manifest.json",
        {
            "arguments": vars(args),
            "utc": datetime.now(timezone.utc),
            "command": command,
            "measurement": "one iteration = five consecutive real HTTP requests and three durable booking writes",
            "expected_http_rps": args.rate * 5,
            "expected_write_tps": args.rate * 3,
            "warmup": {"workflows": args.workers * 8, "connection_reuse": False, "excluded_from_load_metrics": True},
            "source_diff": subprocess.check_output(["git", "diff"], cwd=ROOT, text=True),
            "frozen_source_sha256": source_digest.hexdigest(),
            "workload_sha256": hashlib.sha256((OUT / "workflows.js").read_bytes()).hexdigest(),
            "harness_sha256": {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(HARNESS.iterdir()) if p.is_file()
            },
            "python": sys.version,
            "platform": platform.platform(),
            "hardware": json.loads(subprocess.check_output(["lscpu", "--json"], text=True)),
            "memory": Path("/proc/meminfo").read_text(),
            "host_settings": host_snapshot(),
            "initial_dataset": {
                "tenants": args.tenants,
                "bookings": args.rows,
                "providers_per_tenant": 10,
                "completed_fraction": 0.8,
                "confirmed_fraction": 0.2,
            },
            "dependencies": subprocess.check_output(["uv", "pip", "freeze", "--python", sys.executable], text=True),
            "k6_version": subprocess.check_output(
                [
                    str(Path.home() / ".local/share/axiar-bench-tools/k6-v2.3.0-linux-amd64/k6"),
                    "version",
                ],
                text=True,
            ),
            "postgres": json.loads(docker("inspect", NAMES[0], capture_output=True, text=True).stdout),
            "containers": {name: json.loads(docker("inspect", name, capture_output=True, text=True).stdout) for name in NAMES},
        },
    )
    with (OUT / "api.log").open("w") as log:
        api = subprocess.Popen(
            command,
            cwd=SOURCE / "backend",
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        task = sampler = progress_task = None
        try:
            async with httpx.AsyncClient(base_url=API_URL, timeout=10) as client:
                for _ in range(120):
                    if api.poll() is not None:
                        raise RuntimeError("API exited")
                    try:
                        if (await client.get("/api/v1/health")).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(0.5)
                else:
                    raise RuntimeError("API readiness deadline exceeded")
                identities = json.loads((OUT / "identities.json").read_text())
            warmup_started = time.perf_counter()
            gate = asyncio.Semaphore(args.workers)
            async with httpx.AsyncClient(
                base_url=API_URL,
                timeout=30,
                limits=httpx.Limits(max_keepalive_connections=0, max_connections=args.workers),
            ) as warm_client:

                async def warm_workflow(number):
                    async with gate:
                        who = identities[number % len(identities)]
                        response = await warm_client.get("/api/v1/bookings/?limit=50", headers=who["provider_headers"])
                        assert response.status_code == 200 and len(response.json()) == 50
                        response = await warm_client.post(
                            "/api/v1/bookings/",
                            headers=who["customer_headers"],
                            json={
                                "provider_id": who["provider_id"],
                                "service_id": who["service_id"],
                                "scheduled_time": (
                                    datetime(2029, 1, 1, tzinfo=timezone.utc) + timedelta(hours=number * 2)
                                ).isoformat(),
                                "duration_minutes": 60,
                                "base_price_cents": 5000,
                                "location_postcode": "NG7 2RD",
                                "description": "benchmark-warmup",
                            },
                        )
                        assert response.status_code == 201, response.text
                        booking_id = response.json()["id"]
                        response = await warm_client.patch(
                            f"/api/v1/bookings/{booking_id}/status",
                            headers=who["provider_headers"],
                            json={"status": "confirmed"},
                        )
                        assert response.status_code == 200 and response.json()["status"] == "confirmed"
                        response = await warm_client.get(f"/api/v1/bookings/{booking_id}", headers=who["customer_headers"])
                        assert response.status_code == 200 and response.json()["status"] == "confirmed"
                        response = await warm_client.patch(
                            f"/api/v1/bookings/{booking_id}/status",
                            headers=who["customer_headers"],
                            json={"status": "cancelled"},
                        )
                        assert response.status_code == 200 and response.json()["status"] == "cancelled"

                await asyncio.gather(*(warm_workflow(number) for number in range(args.workers * 8)))
            conn = await asyncpg.connect(DB_URL.replace("postgresql+asyncpg", "postgresql"))
            try:
                for _ in range(120):
                    pending = await conn.fetchval("SELECT count(*) FROM outbox_messages WHERE status!='published'")
                    if pending == 0:
                        break
                    await asyncio.sleep(0.25)
                assert pending == 0, "Warmup events must drain before load"
            finally:
                await conn.close()
            save(
                "warmup.json",
                {
                    "workflows": args.workers * 8,
                    "elapsed_seconds": time.perf_counter() - warmup_started,
                    "pending_events_at_load_start": pending,
                    "description": "benchmark-warmup",
                },
            )
            workers_before = worker_snapshot(metric_dir)
            save("workers-before.json", workers_before)
            metrics_before = collect_metrics(metric_dir)
            with gzip.open(OUT / "metrics-before.txt.gz", "wb") as f:
                f.write(metrics_before)
            task = asyncio.create_task(
                monitor(
                    api.pid, container_cgroups((*NAMES, "axiar-bench-proxy") if args.balancer != "shared_socket" else NAMES)
                )
            )
            if args.cprofile:
                os.kill(api.pid, signal.SIGUSR2)
                await asyncio.sleep(0.1)
            conn = await asyncpg.connect(DB_URL.replace("postgresql+asyncpg", "postgresql"))
            await conn.execute("SELECT pg_stat_statements_reset()")
            await conn.close()
            if args.sample:
                sampler = subprocess.Popen(
                    [
                        "sudo",
                        "-n",
                        str(ROOT / "backend/.venv/bin/py-spy"),
                        "record",
                        *(["--native"] if args.native_profile else []),
                        "--rate",
                        "50" if args.native_profile else "100",
                        "--pid",
                        str(api.pid),
                        "--subprocesses",
                        "--duration",
                        "20",
                        "--format",
                        "speedscope",
                        "--output",
                        str(OUT / "profile.json"),
                    ],
                    stdout=log,
                    stderr=log,
                )
            k6 = Path.home() / ".local/share/axiar-bench-tools/k6-v2.3.0-linux-amd64/k6"
            with (OUT / "k6.log").open("w") as loadlog:
                load = await asyncio.create_subprocess_exec(
                    str(k6),
                    "run",
                    *(["--address=127.0.0.1:56565"] if args.live_status else []),
                    "--quiet",
                    "--out",
                    f'json={OUT/"raw.ndjson.gz"}',
                    str(OUT / "workflows.js"),
                    env=env,
                    stdout=loadlog,
                    stderr=loadlog,
                )
                LOAD_PID = load.pid
                if args.live_status:
                    progress_task = asyncio.create_task(live_status())
                code = await load.wait()
                if progress_task:
                    progress_task.cancel()
                    await asyncio.gather(progress_task, return_exceptions=True)
                if task.done() and not task.cancelled() and task.exception():
                    raise RuntimeError("Resource monitoring failed") from task.exception()
            if code not in (0, 99):
                raise RuntimeError(f"k6 exited with {code}")
            if sampler:
                # Native symbol resolution/export can outlive the load window.
                # Do not silently kill the recorder and claim a profile exists.
                try:
                    await asyncio.wait_for(asyncio.to_thread(sampler.wait), timeout=60)
                except TimeoutError:
                    raise RuntimeError("Profiler did not finish; inspect api.log")
                if sampler.returncode != 0 or not (OUT / "profile.json").exists():
                    raise RuntimeError("Profiler failed to produce a stack trace; inspect api.log")
            if args.cprofile:
                os.kill(api.pid, signal.SIGUSR1)
                await asyncio.sleep(0.5)
            workers_after = worker_snapshot(metric_dir)
            save("workers-after.json", workers_after)
            save(
                "worker-distribution.json",
                {
                    pid: {
                        "http_responses": row["responses"] - workers_before.get(pid, {}).get("responses", 0),
                        "cpu_seconds": row["cpu_s"] - workers_before.get(pid, {}).get("cpu_s", 0),
                        "nice": row["nice"],
                        "affinity": row["affinity"],
                        "database_pool": args.pool,
                    }
                    for pid, row in workers_after.items()
                },
            )
            metrics_after = collect_metrics(metric_dir)
            with gzip.open(OUT / "metrics-after.txt.gz", "wb") as f:
                f.write(metrics_after)
            postload_started = time.perf_counter()
            conn = await asyncpg.connect(DB_URL.replace("postgresql+asyncpg", "postgresql"))
            try:
                for _ in range(240):
                    remaining = await conn.fetchval("""
                        SELECT count(*) FROM outbox_messages o JOIN bookings b ON b.id=o.aggregate_id
                        WHERE b.description='benchmark-extremes' AND o.status!='published'
                    """)
                    if remaining == 0:
                        break
                    await asyncio.sleep(0.25)
                postload_drain_seconds = time.perf_counter() - postload_started
                acknowledged_ids = {}
                with gzip.open(OUT / "raw.ndjson.gz", "rt") as raw:
                    for line in raw:
                        if '"completed_workflows"' not in line:
                            continue
                        point = json.loads(line)
                        if point.get("type") == "Point" and point.get("metric") == "completed_workflows":
                            meta = point["data"]["metadata"]
                            acknowledged_ids[meta["booking_id"]] = (meta["tenant_id"], meta["provider_id"])
                verified_ids = verified_audits = verified_outbox = 0
                id_list = list(acknowledged_ids)
                for start in range(0, len(id_list), 5000):
                    rows = await conn.fetch(
                        "SELECT id,tenant_id,provider_id,status FROM bookings WHERE id=ANY($1::uuid[])",
                        id_list[start : start + 5000],
                    )
                    verified_ids += sum(
                        row["status"] == "CANCELLED"
                        and (str(row["tenant_id"]), str(row["provider_id"])) == acknowledged_ids[str(row["id"])]
                        for row in rows
                    )
                    audits = await conn.fetch(
                        """
                        SELECT entity_id,tenant_id,count(*) n FROM audit_logs
                        WHERE entity_type='booking' AND entity_id=ANY($1::uuid[]) GROUP BY entity_id,tenant_id
                    """,
                        id_list[start : start + 5000],
                    )
                    verified_audits += sum(
                        row["n"] == 3 and str(row["tenant_id"]) == acknowledged_ids[str(row["entity_id"])][0] for row in audits
                    )
                    events = await conn.fetch(
                        """
                        SELECT aggregate_id,tenant_id,array_agg(event_type ORDER BY event_type) types
                        FROM outbox_messages WHERE aggregate_type='booking' AND aggregate_id=ANY($1::uuid[])
                        GROUP BY aggregate_id,tenant_id
                    """,
                        id_list[start : start + 5000],
                    )
                    verified_outbox += sum(
                        row["types"] == ["booking.cancelled", "booking.confirmed", "booking.created"]
                        and str(row["tenant_id"]) == acknowledged_ids[str(row["aggregate_id"])][0]
                        for row in events
                    )
                counts = [
                    dict(row)
                    for row in await conn.fetch(
                        "SELECT status,count(*) FROM bookings WHERE description='benchmark-extremes' GROUP BY status"
                    )
                ]
                outbox = [dict(row) for row in await conn.fetch("""
                    SELECT o.status,count(*) FROM outbox_messages o JOIN bookings b ON b.id=o.aggregate_id
                    WHERE b.description='benchmark-extremes' GROUP BY o.status
                """)]
                violations = await conn.fetchval("""
                    SELECT count(*) FROM bookings b JOIN providers p ON p.id=b.provider_id JOIN services s ON s.id=b.service_id
                    JOIN users u ON u.id=b.customer_id WHERE b.tenant_id!=p.tenant_id OR b.tenant_id!=s.tenant_id
                    OR b.tenant_id!=u.tenant_id OR s.provider_id!=p.id
                """)
                overlaps = await conn.fetchval("""
                    SELECT count(*) FROM (SELECT scheduled_time,lag(scheduled_time + duration_minutes*interval '1 minute')
                    OVER (PARTITION BY tenant_id,provider_id ORDER BY scheduled_time) AS previous_end
                    FROM bookings WHERE status IN
                    ('PENDING','CONFIRMED','ASSIGNED','ON_MY_WAY','ARRIVED','DELAYED','IN_PROGRESS')) q
                    WHERE scheduled_time<previous_end
                """)
                save(
                    "query-statistics.json",
                    [dict(row) for row in await conn.fetch("""
                    SELECT query,calls,total_exec_time,mean_exec_time,rows,shared_blks_hit,shared_blks_read,wal_bytes
                    FROM pg_stat_statements WHERE dbid=(SELECT oid FROM pg_database WHERE datname=current_database())
                    ORDER BY total_exec_time DESC
                """)],
                )
            finally:
                await conn.close()
            summary = json.loads((OUT / "k6-summary.json").read_text())["metrics"]
            cancelled = sum(row["count"] for row in counts if row["status"] == "CANCELLED")
            complete = summary.get("completed_workflows", {}).get("values", {}).get("count", 0)
            save(
                "verification.json",
                {
                    "k6_exit": code,
                    "statuses": counts,
                    "outbox": outbox,
                    "outbox_scope": "only measured-workflow bookings; warmup excluded",
                    "postload_outbox_drain_seconds": postload_drain_seconds,
                    "outbox_not_published_after_deadline": remaining,
                    "cross_tenant_references": violations,
                    "overlapping_active_intervals": overlaps,
                    "persisted_completed_workflows": cancelled,
                    "reported_completed_workflows": complete,
                    "individually_verified_acknowledged_ids": verified_ids,
                    "acknowledged_bookings_with_three_atomic_audits": verified_audits,
                    "acknowledged_bookings_with_three_outbox_events": verified_outbox,
                    "server_http_responses_delta": response_count(metrics_after) - response_count(metrics_before),
                    "acknowledged_distinct_tenants": len({who[0] for who in acknowledged_ids.values()}),
                    "acknowledged_distinct_providers": len({who[1] for who in acknowledged_ids.values()}),
                    "committed_cancellations_without_client_success": max(0, cancelled - complete),
                    "final_process_resources": processes(api.pid),
                },
            )
            assert cancelled >= complete, "A client-acknowledged workflow must have a durable cancelled booking"
            assert (
                len(acknowledged_ids) == verified_ids == complete
            ), "Every reported workflow ID must be durable in its owning tenant"
            assert verified_audits == verified_outbox == complete, "Each completed booking must retain its three audits/events"
            assert violations == 0 and overlaps == 0
        finally:
            if progress_task:
                progress_task.cancel()
                await asyncio.gather(progress_task, return_exceptions=True)
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            if sampler and sampler.poll() is None:
                sampler.terminate()
                sampler.wait(timeout=10)
            if api.poll() is None:
                os.killpg(api.pid, signal.SIGTERM)
                try:
                    api.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    os.killpg(api.pid, signal.SIGKILL)
                    api.wait()
            (OUT / "identities.json").unlink(missing_ok=True)
    print(
        json.dumps(
            {
                "successful_workflows": summary.get("completed_workflows", {}).get("values"),
                "failed_workflows": summary.get("workflow_errors", {}).get("values", {}).get("passes", 0),
                "workflow_error_rate": summary.get("workflow_errors", {}).get("values", {}).get("rate", 0),
                "workflow_latency_ms": summary.get("workflow_duration_ms", {}).get("values"),
                "http_requests": summary.get("http_reqs", {}).get("values"),
                "dropped_workflow_arrivals": summary.get("dropped_iterations", {}).get("values", {}).get("count", 0),
                "raw_k6_summary": str(OUT / "k6-summary.json"),
            }
        ),
        flush=True,
    )


asyncio.run(main())
