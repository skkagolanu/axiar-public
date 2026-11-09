"""Summarise every completed worker-distribution probe, including failed offers."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
rows = []
for folder in sorted((ROOT / "results").glob("distribution-*")):
    path = folder / "derived-metrics.json"
    if not path.exists():
        continue
    report = json.loads(path.read_text())
    workers = report["worker_balance"]
    counts = [worker["http_responses"] for worker in workers["workers"].values()]
    kafka_path = folder / "kafka-audit.json"
    row = {
        "label": folder.name,
        "arguments": report["arguments"],
        "backend_sha256": report["source_sha256"],
        "workload_sha256": report["workload_sha256"],
        "completed_workflows": report["successful_workflow_count"],
        "completed_workflows_per_second": report["completed_workflows"]["rate"],
        "workflow_p99_ms": report["workflow_latency_ms"]["p(99)"],
        "failed_started_workflows": report["failed_started_workflow_count"],
        "dropped_arrivals": report["dropped_arrivals"],
        "minimum_worker_requests": min(counts),
        "maximum_worker_requests": max(counts),
        "max_to_min_worker_requests": workers["max_to_min_requests"],
        "worker_request_cv": workers["request_coefficient_of_variation"],
        "equal_worker_configuration": workers["all_equal_pool_nice_affinity"],
        "api_cpu_ms_per_workflow": report["api_cpu_ms_per_completed_workflow"],
        "application_cpu_ms_per_workflow_including_proxy": report["application_cpu_ms_per_completed_workflow"],
        "verification": report["verification"],
        "independent_kafka_audit": json.loads(kafka_path.read_text()) if kafka_path.exists() else None,
    }
    rows.append(row)
(ROOT / "results/worker-distribution.json").write_text(json.dumps(rows, indent=2) + "\n")
lines = [
    "# Worker distribution measurements",
    "",
    "One workflow is five consecutive authenticated HTTP requests and three committed booking writes. "
    "These local synthetic probes retain full response bodies, tenant authorization and durable outbox writes.",
    "",
    "| Experiment | Duration | Offered workflows/s | Completed/s | p99 ms | Drops | "
    "Worker requests min–max | Max/min | CPU ms/workflow* |",
    "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
]
for row in rows:
    lines.append(
        f'| {row["label"]} | {row["arguments"]["duration"]} | {row["arguments"]["rate"]} | '
        f'{row["completed_workflows_per_second"]:.2f} | {row["workflow_p99_ms"]:.2f} | '
        f'{row["dropped_arrivals"]} | {row["minimum_worker_requests"]:.0f}–{row["maximum_worker_requests"]:.0f} | '
        f'{row["max_to_min_worker_requests"]:.3f} | '
        f'{row["application_cpu_ms_per_workflow_including_proxy"]:.2f} |'
    )
lines.extend(
    [
        "",
        "*CPU cost includes API, PostgreSQL, Redis, Kafka and proxy (when used); excludes load generator. "
        "The two-second sampling window extends from after warmup through verification. "
        "CPU time per workflow is not CPU utilisation.",
        "",
        "Shared-socket versus least-connections 12-worker pairs preserve backend/workload hashes, pool=4, "
        "PostgreSQL 4 CPUs/3 GiB, Kafka 2 GiB and 256 VUs. The eight-worker probe uses pool=6 "
        "(same total pool budget) and 64 VUs; it changes multiple setup parameters and is not a single-variable comparison.",
        "",
        "Short sequential probes establish neither repeatable ten-minute capacity nor a production/CV achievement. "
        "The 500/sec/<10-ms stretch target remains unmet. Improved 200/sec latency came with increased measured CPU cost.",
        "",
        "Rebuild this report: `backend/.venv/bin/python benchmarks/distribution_report.py`. "
        "Raw metrics, full worker deltas, frozen backend/harness, manifests, database verifications and independent "
        "Kafka ledgers are retained under `benchmarks/results/<experiment>/`. "
        "Machine-readable summaries: `benchmarks/results/worker-distribution.json`.",
    ]
)
(ROOT / "worker-distribution.md").write_text("\n".join(lines) + "\n")
