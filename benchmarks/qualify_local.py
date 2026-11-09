"""Qualify configured workload levels and retain every measured repetition."""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "benchmarks/results"
STATE = RESULTS / "local-qualification.json"


def evaluate(label):
    folder = RESULTS / label
    manifest = json.loads((folder / "manifest.json").read_text())
    arguments = manifest["arguments"]
    metrics = json.loads((folder / "k6-summary.json").read_text())["metrics"]

    def value(name, field, default=None):
        return metrics.get(name, {}).get("values", {}).get(field, default)

    verified = json.loads((folder / "verification.json").read_text())
    kafka = json.loads((folder / "kafka-audit.json").read_text())
    completed = value("completed_workflows", "count", 0)
    durable = {row["name"]: row["setting"] for row in json.loads((folder / "durability.json").read_text())}
    checks = {
        "ten_minute_window": arguments["duration"] in ("10m", "600s"),
        "no_profile_or_interruption": not any(arguments.get(k, False) for k in ("sample", "cprofile", "native_profile"))
        and not (folder / "interrupted.json").exists(),
        "zero_failed_started_workflows": value("workflow_errors", "rate") == 0,
        "zero_dropped_arrivals": value("dropped_iterations", "count", 0) == 0,
        "p99_below_500ms": value("workflow_duration_ms", "p(99)", float("inf")) < 500,
        "all_started_workflows_completed": completed > 0 and value("workflow_attempts", "count") == completed,
        "durable_ids_audits_events": all(
            verified.get(key) == completed
            for key in (
                "individually_verified_acknowledged_ids",
                "acknowledged_bookings_with_three_atomic_audits",
                "acknowledged_bookings_with_three_outbox_events",
            )
        ),
        "all_tenants_and_providers_exercised": verified.get("acknowledged_distinct_tenants") == 100
        and verified.get("acknowledged_distinct_providers") == 1000,
        "no_overlaps_or_tenant_reference_errors": verified.get("overlapping_active_intervals") == 0
        and verified.get("cross_tenant_references") == 0,
        "http_counter_reconciled": verified.get("server_http_responses_delta") == value("http_reqs", "count") == completed * 5,
        "all_events_independently_observed": kafka.get("expected_committed_outbox_events") == completed * 3
        and kafka.get("independently_observed_outbox_ids") == completed * 3
        and not kafka.get("missing_outbox_ids")
        and kafka.get("payload_or_tenant_mismatches") == 0,
        "postgres_durability_enabled": all(
            durable.get(key) == "on" for key in ("fsync", "synchronous_commit", "full_page_writes")
        ),
    }
    if arguments.get("balancer", "shared_socket") != "shared_socket":
        balance = json.loads((folder / "derived-metrics.json").read_text())["worker_balance"]
        checks["balanced_workers_with_equal_configuration"] = (
            len(balance["workers"]) == arguments["workers"]
            and balance["all_equal_pool_nice_affinity"]
            and balance["max_to_min_requests"] is not None
            and balance["max_to_min_requests"] <= 1.25
            and balance["total_responses"] == completed * 5
        )
    return {
        "label": label,
        "passed": all(checks.values()),
        "checks": checks,
        "offered_workflows_per_second": arguments["rate"],
        "actual_completed_workflows_per_second": value("completed_workflows", "rate"),
        "completed_workflows": completed,
        "p99_ms": value("workflow_duration_ms", "p(99)"),
        "dropped_arrivals": value("dropped_iterations", "count", 0),
        "source_sha256": manifest["frozen_source_sha256"],
        "workload_sha256": manifest["workload_sha256"],
        "configuration": {
            key: arguments.get(key, {"balancer": "shared_socket", "shared_buffers_mib": 128}.get(key, False))
            for key in (
                "workers",
                "pool",
                "db_cpus",
                "db_memory_mib",
                "kafka_memory_mib",
                "vus",
                "tenants",
                "rows",
                "live_status",
                "balancer",
                "shared_buffers_mib",
            )
        },
        "harness_sha256": manifest.get("harness_sha256"),
    }


def main():
    global STATE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--existing", required=True, help="First completed 200/sec experiment with independent Kafka audit")
    parser.add_argument("--state", type=Path, default=STATE)
    parser.add_argument("--prefix", default="local-qualified")
    parser.add_argument("--balancer", choices=("shared_socket", "least_conn", "round_robin"), default="shared_socket")
    parser.add_argument("--workers", type=int)
    parser.add_argument("--pool", type=int)
    args = parser.parse_args()
    STATE = args.state
    if STATE.exists():
        raise RuntimeError("Qualification state already exists; review it rather than overwriting evidence")
    state = {
        "target": "3 x 10 minutes; p99 <500ms; zero drops/errors; complete correctness/event reconciliation",
        "runs": [],
        "qualified_rate": None,
        "status": "running",
    }

    def save():
        state["updated_utc"] = datetime.now(timezone.utc).isoformat()
        STATE.write_text(json.dumps(state, indent=2) + "\n")

    first = evaluate(args.existing)
    state["runs"].append(first)
    save()
    source = RESULTS / args.existing / "source"
    for rate in (200, 150):
        passes = [first] if rate == 200 and first["passed"] else []
        if rate == 200 and not first["passed"]:
            continue
        for repetition in range(len(passes), 3):
            label = f"{args.prefix}-{rate}-r{repetition}"
            state["next_run"] = label
            save()
            command = [
                sys.executable,
                str(ROOT / "benchmarks/sustain.py"),
                "--source",
                str(source),
                "--label",
                label,
                "--workers",
                str(args.workers or (12 if rate == 200 else 8)),
                "--pool",
                str(args.pool or (4 if rate == 200 else 8)),
                "--balancer",
                args.balancer,
                "--db-cpus",
                "4",
                "--db-memory-mib",
                "3072",
                "--kafka-memory-mib",
                "2048",
                "--rate",
                str(rate),
                "--vus",
                "256",
                "--duration",
                "10m",
            ]
            print(f"Starting {label}", flush=True)
            with (RESULTS / f"{label}.log").open("w") as log:
                subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
                subprocess.run(
                    [sys.executable, str(ROOT / "benchmarks/kafka_audit.py"), str(RESULTS / label)],
                    cwd=ROOT,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=True,
                )
                subprocess.run(
                    [sys.executable, str(ROOT / "benchmarks/metrics_report.py"), str(RESULTS / label)],
                    cwd=ROOT,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=True,
                )
            result = evaluate(label)
            state["runs"].append(result)
            if passes:
                reference = passes[0]
                for key in ("source_sha256", "workload_sha256", "configuration"):
                    assert result[key] == reference[key], f"Incompatible comparison: {key}"
            save()
            print(json.dumps(result), flush=True)
            if not result["passed"]:
                break
            passes.append(result)
        if len(passes) == 3:
            state.update(qualified_rate=rate, status="qualified", next_run=None)
            save()
            print(
                f"Qualified nominal {rate} workflows/sec in three ten-minute runs; see actual rates and limits in {STATE}",
                flush=True,
            )
            return
    state.update(status="no_level_qualified", next_run=None)
    save()
    raise SystemExit(1)


if __name__ == "__main__":
    main()
