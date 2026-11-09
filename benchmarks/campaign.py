"""Alternating baseline/candidate campaigns at configurable dataset and arrival-rate levels."""

import argparse
import asyncio
import gzip
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
import httpx
from environment import API_URL, DB_URL, NAMES, docker, environment
from prometheus_client.parser import text_string_to_metric_families

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--label", required=True)
parser.add_argument("--duration", default="10m")
parser.add_argument("--repeats", type=int, default=3)
parser.add_argument("--profile", choices=["both", "low", "high"], default="both")
parser.add_argument("--k6", type=Path, default=Path.home() / ".local/share/axiar-bench-tools/k6-v2.3.0-linux-amd64/k6")
parser.add_argument("--baseline", type=Path, default=Path("/tmp/axiar-benchmark-baseline"))
parser.add_argument(
    "--profile-api", action="store_true", help="Diagnostic CPU profile; never use for reported latency results"
)
args = parser.parse_args()
OUT = ROOT / "benchmarks/results" / args.label
OUT.mkdir(parents=True, exist_ok=False)
HARNESS = OUT / "harness"
HARNESS.mkdir()
for filename in ["environment.py", "fixture.py", "extremes.js", "campaign.py"]:
    shutil.copy2(ROOT / "benchmarks" / filename, HARNESS / filename)


def source_hash(source):
    digest = hashlib.sha256()
    for path in sorted((source / "backend").rglob("*.py")):
        if ".venv" in path.parts or "__pycache__" in path.parts:
            continue
        digest.update(str(path.relative_to(source)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, default=str) + "\n")


def freeze_candidate():
    dest = OUT / "candidate-source"
    files = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).split(b"\0")
    files += subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard", "-z", "backend"], cwd=ROOT).split(
        b"\0"
    )
    for encoded in files:
        if not encoded:
            continue
        relative = Path(os.fsdecode(encoded))
        if not (ROOT / relative).is_file():
            continue
        target = dest / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    (OUT / "candidate.diff").write_text(subprocess.check_output(["git", "diff"], cwd=ROOT, text=True))
    return dest


async def wait_api(process):
    async with httpx.AsyncClient(base_url=API_URL, timeout=2) as client:
        for _ in range(120):
            if process.poll() is not None:
                raise RuntimeError("API exited; see the run's api.log")
            try:
                if (await client.get("/api/v1/health")).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.5)
    raise RuntimeError("API readiness deadline exceeded")


def stop(process):
    process.terminate()
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


async def metrics(client, headers, path):
    response = await client.get("/api/v1/metrics", headers=headers, timeout=120)
    response.raise_for_status()
    with gzip.open(path, "wt") as stream:
        stream.write(response.text)
    counts = {}
    for family in text_string_to_metric_families(response.text):
        for sample in family.samples:
            if sample.name == "http_requests_total":
                key = (sample.labels["method"], sample.labels["endpoint"], sample.labels["status"])
                counts[key] = sample.value
    return counts


def api_resource(pid):
    try:
        stat = Path(f"/proc/{pid}/stat").read_text().split()
        status = Path(f"/proc/{pid}/status").read_text().splitlines()
        rss_kib = int(next(line for line in status if line.startswith("VmRSS:")).split()[1])
        return {"cpu_s": (int(stat[13]) + int(stat[14])) / os.sysconf("SC_CLK_TCK"), "rss_kib": rss_kib}
    except (OSError, StopIteration):
        return {}


async def inspect_database():
    conn = await asyncpg.connect(DB_URL.replace("postgresql+asyncpg", "postgresql"))
    try:
        assert await conn.fetchval("SELECT current_database()") == "axiar_benchmark"
        statuses = await conn.fetch(
            "SELECT status, count(*) FROM bookings WHERE description='benchmark-extremes' GROUP BY status"
        )
        # A lag detects an overlap without quadratic self-joins. Intervals are fixed
        # to 60 minutes in this fixture, including all workload-created bookings.
        conflicts = await conn.fetchval("""
            SELECT count(*) FROM (
                SELECT scheduled_time, lag(scheduled_time + duration_minutes * interval '1 minute')
                OVER (PARTITION BY tenant_id, provider_id ORDER BY scheduled_time) AS previous_end
                FROM bookings WHERE status IN ('PENDING','CONFIRMED','ASSIGNED','ON_MY_WAY','ARRIVED','DELAYED','IN_PROGRESS')
            ) slots WHERE scheduled_time < previous_end
        """)
        mismatches = await conn.fetchval("""
            SELECT count(*) FROM bookings b JOIN providers p ON p.id=b.provider_id
            JOIN services s ON s.id=b.service_id JOIN users u ON u.id=b.customer_id
            WHERE b.tenant_id!=p.tenant_id OR b.tenant_id!=s.tenant_id OR b.tenant_id!=u.tenant_id OR s.provider_id!=p.id
        """)
        outbox = await conn.fetch("SELECT status,count(*) FROM outbox_messages GROUP BY status")
        return {
            "workflow_booking_statuses": [dict(row) for row in statuses],
            "overlapping_active_intervals": conflicts,
            "cross_tenant_or_provider_references": mismatches,
            "outbox_statuses": [dict(row) for row in outbox],
        }
    finally:
        await conn.close()


async def monitor(process, output):
    with output.open("w") as stream:
        while process.poll() is None:
            sample = {"utc": datetime.now(timezone.utc).isoformat(), "api": api_resource(process.pid)}
            conn = await asyncpg.connect(DB_URL.replace("postgresql+asyncpg", "postgresql"))
            try:
                sample["database"] = dict(await conn.fetchrow("""
                    SELECT xact_commit,xact_rollback,blks_read,blks_hit,tup_returned,tup_fetched,tup_inserted,deadlocks
                    FROM pg_stat_database WHERE datname=current_database()
                """))
                sample["db_waiters"] = await conn.fetchval("""
                    SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock'
                """)
            finally:
                await conn.close()
            stream.write(json.dumps(sample) + "\n")
            stream.flush()
            await asyncio.sleep(5)


async def one_run(source, version, name, tenants, rows, rps, repeat):
    run = OUT / f"{name}-{version}-{repeat}"
    run.mkdir()
    env = environment()
    fixture = run / "identities.json"
    with (run / "seed.log").open("w") as log:
        subprocess.run(
            [
                sys.executable,
                str(HARNESS / "fixture.py"),
                "--source",
                str(source),
                "--tenants",
                str(tenants),
                "--rows",
                str(rows),
                "--output",
                str(fixture),
            ],
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
        )
    env["PYTHONPATH"] = str(source / "backend")
    command_api = [
        sys.executable,
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
    ]
    if args.profile_api:
        env["PROFILE_PATH"] = str(run / "cpu-profile.pstats")
        command_api = [sys.executable, str(ROOT / "benchmarks/profile_server.py")]
    with (run / "api.log").open("w") as log:
        api = subprocess.Popen(
            command_api,
            cwd=source / "backend",
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        monitor_task = None
        try:
            await wait_api(api)
            identities = json.loads(fixture.read_text())
            async with httpx.AsyncClient(base_url=API_URL, timeout=60) as client:
                for who in identities[: min(100, len(identities))]:
                    response = await client.get("/api/v1/bookings/?limit=50", headers=who["provider_headers"])
                    assert response.status_code == 200, response.text
                before = await metrics(client, identities[0]["customer_headers"], run / "metrics-before.txt.gz")
                monitor_task = asyncio.create_task(monitor(api, run / "resources.ndjson"))
                env.update(
                    API_URL=API_URL,
                    OFFERED_RPS=str(rps),
                    DURATION=args.duration,
                    FIXTURE_PATH=str(fixture),
                    SUMMARY_PATH=str(run / "k6-summary.json"),
                    K6_NO_USAGE_REPORT="true",
                )
                command = [
                    str(args.k6),
                    "run",
                    "--quiet",
                    "--out",
                    f"json={run / 'k6-raw.ndjson.gz'}",
                    str(HARNESS / "extremes.js"),
                ]
                save(
                    run / "manifest.json",
                    {
                        "profile": name,
                        "version": version,
                        "source": source,
                        "tenants": tenants,
                        "bookings": rows,
                        "offered_rps": rps,
                        "repeat": repeat,
                        "duration": args.duration,
                        "warmup": "100 authenticated schedule reads, no writes",
                        "command": command,
                        "utc_started": datetime.now(timezone.utc),
                        "before_api_resource": api_resource(api.pid),
                    },
                )
                started = time.perf_counter()
                with (run / "k6.log").open("w") as k6log:
                    load = await asyncio.create_subprocess_exec(*command, cwd=ROOT, env=env, stdout=k6log, stderr=k6log)
                    returncode = await load.wait()
                # k6 exit 99 means thresholds failed; the measurement is retained as a failed load level.
                if returncode not in (0, 99):
                    raise RuntimeError(f"k6 failed with exit {returncode}; see {run / 'k6.log'}")
                after = await metrics(client, identities[0]["customer_headers"], run / "metrics-after.txt.gz")
                resource = api_resource(api.pid)
                invariant = await inspect_database()
                delta = sum(
                    value - before.get(key, 0) for key, value in after.items() if key[1].startswith("/api/v1/bookings")
                )
                save(
                    run / "verification.json",
                    {
                        **invariant,
                        "api_counter_booking_requests_delta": delta,
                        "booking_route_label_count": len({key[1] for key in after if key[1].startswith("/api/v1/bookings")}),
                        "after_api_resource": resource,
                        "elapsed_including_collection_s": time.perf_counter() - started,
                        "k6_exit_code": returncode,
                    },
                )
                assert invariant["overlapping_active_intervals"] == 0
                assert invariant["cross_tenant_or_provider_references"] == 0
        finally:
            if monitor_task:
                monitor_task.cancel()
                await asyncio.gather(monitor_task, return_exceptions=True)
            stop(api)
    # Tokens are disposable fixture material; the deterministic generator reproduces them.
    fixture.unlink()
    return str(run)


async def main():
    candidate = freeze_candidate()
    save(
        OUT / "manifest.json",
        {
            "arguments": vars(args),
            "baseline_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "utc": datetime.now(timezone.utc),
            "python": sys.version,
            "platform": platform.platform(),
            "cpu": Path("/proc/cpuinfo").read_text().split("model name", 1)[-1].splitlines()[0],
            "memory": Path("/proc/meminfo").read_text().splitlines()[:3],
            "workers": 1,
            "pool_size": 30,
            "max_overflow": 30,
            "rate_limit_enabled": False,
            "demo_mode": False,
            "dataset": "80% completed in 2025, 20% confirmed in 2027; ten providers per tenant",
            "baseline_source_sha256": source_hash(args.baseline.resolve()),
            "candidate_source_sha256": source_hash(candidate),
            "images": json.loads(docker("inspect", *NAMES, capture_output=True, text=True).stdout),
            "k6_version": subprocess.check_output([str(args.k6), "version"], text=True),
            "k6_script_sha256": hashlib.sha256((ROOT / "benchmarks/extremes.js").read_bytes()).hexdigest(),
            "fixture_script_sha256": hashlib.sha256((ROOT / "benchmarks/fixture.py").read_bytes()).hexdigest(),
            "dependencies": subprocess.check_output(["uv", "pip", "freeze", "--python", sys.executable], text=True),
        },
    )
    completed = []
    for name, tenants, rows, rps in [("low", 10, 10000, 10), ("high", 100, 100000, 500)]:
        if args.profile not in ("both", name):
            continue
        for repeat in range(args.repeats):
            order = [("baseline", args.baseline.resolve()), ("candidate", candidate)]
            if repeat % 2:
                order.reverse()
            for version, source in order:
                print(f"START {name} {version} repeat={repeat} offered={rps}RPS duration={args.duration}", flush=True)
                completed.append(await one_run(source, version, name, tenants, rows, rps, repeat))
                save(OUT / "progress.json", {"completed": completed, "updated": datetime.now(timezone.utc)})
                print(f"DONE {name} {version} repeat={repeat}", flush=True)
    save(OUT / "complete.json", {"completed": completed, "updated": datetime.now(timezone.utc)})


asyncio.run(main())
