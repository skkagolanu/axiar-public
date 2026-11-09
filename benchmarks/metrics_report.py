"""Derive auditable metrics for one completed strict-workflow experiment."""

import argparse
import gzip
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


def percentile(values, fraction):
    ordered = sorted(values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def distribution(values):
    return {
        "count": len(values),
        "p50_ms": percentile(values, 0.5),
        "p95_ms": percentile(values, 0.95),
        "p99_ms": percentile(values, 0.99),
        "max_ms": max(values) if values else None,
    }


def process_cpu(samples, key):
    earliest, latest = {}, {}
    for sample in samples:
        for process in sample.get(key, []):
            earliest.setdefault(process["pid"], process["cpu_s"])
            latest[process["pid"]] = process["cpu_s"]
    return sum(latest[pid] - value for pid, value in earliest.items())


def report(folder):
    manifest = json.loads((folder / "manifest.json").read_text())
    metrics = json.loads((folder / "k6-summary.json").read_text())["metrics"]
    verification = json.loads((folder / "verification.json").read_text())

    def values(name):
        return metrics.get(name, {}).get("values", {})

    operations = defaultdict(list)
    statuses = Counter()
    with gzip.open(folder / "raw.ndjson.gz", "rt") as stream:
        for line in stream:
            if '"operation_duration_ms"' not in line and '"http_req_duration"' not in line:
                continue
            point = json.loads(line)
            if point.get("type") != "Point":
                continue
            data = point["data"]
            if point["metric"] == "operation_duration_ms":
                operations[data["tags"]["operation"]].append(data["value"])
            elif point["metric"] == "http_req_duration":
                statuses[data["tags"].get("status", "unknown")] += 1
    samples = [json.loads(line) for line in (folder / "resources.ndjson").read_text().splitlines() if line.strip()]
    api_cpu = process_cpu(samples, "processes")
    load_cpu = process_cpu(samples, "load_generator")
    window_seconds = (datetime.fromisoformat(samples[-1]["utc"]) - datetime.fromisoformat(samples[0]["utc"])).total_seconds()
    logical_cpus = next(
        (int(row["data"]) for row in manifest.get("hardware", {}).get("lscpu", []) if row["field"] == "CPU(s):"), None
    )
    host_cpu_utilisation = None
    if "host" in samples[0] and "host" in samples[-1]:
        first_ticks = list(map(int, samples[0]["host"]["cpu"].splitlines()[0].split()[1:9]))
        last_ticks = list(map(int, samples[-1]["host"]["cpu"].splitlines()[0].split()[1:9]))
        ticks = [end - start for start, end in zip(first_ticks, last_ticks)]
        if sum(ticks):
            host_cpu_utilisation = 100 * (sum(ticks) - ticks[3] - ticks[4] - ticks[7]) / sum(ticks)
    containers = {}
    for name in samples[-1].get("containers", {}):
        observed = [sample["containers"][name] for sample in samples if name in sample.get("containers", {})]

        def cpu(row):
            return int(dict(line.split() for line in row["cpu.stat"].splitlines())["usage_usec"]) / 1e6

        containers[name] = {
            "cpu_seconds_sampling_window": cpu(observed[-1]) - cpu(observed[0]),
            "peak_observed_memory_mib": max(int(row["memory.current"]) for row in observed) / 2**20,
            "cpu_stat_before": observed[0]["cpu.stat"],
            "cpu_stat_after": observed[-1]["cpu.stat"],
            "io_stat_before": observed[0].get("io.stat"),
            "io_stat_after": observed[-1].get("io.stat"),
        }
    complete = values("completed_workflows").get("count", 0)
    attempts = values("workflow_attempts").get("count", 0)
    dropped = values("dropped_iterations").get("count", 0)
    total_app_cpu = api_cpu + sum(row["cpu_seconds_sampling_window"] for row in containers.values())
    host_temperatures = defaultdict(list)
    for sample in samples:
        for path, value in sample.get("host", {}).get("sensor_temperatures", {}).items():
            host_temperatures[path].append(int(value) / 1000)
    workers = (
        json.loads((folder / "worker-distribution.json").read_text()) if (folder / "worker-distribution.json").exists() else {}
    )
    request_counts = [row["http_responses"] for row in workers.values()]
    worker_balance = {
        "workers": workers,
        "total_responses": sum(request_counts),
        "max_to_min_requests": max(request_counts) / min(request_counts) if request_counts and min(request_counts) else None,
        "request_coefficient_of_variation": (
            statistics.pstdev(request_counts) / statistics.mean(request_counts)
            if request_counts and sum(request_counts)
            else None
        ),
        "all_equal_pool_nice_affinity": (
            len({(row["database_pool"], row["nice"], tuple(row["affinity"])) for row in workers.values()}) == 1
            if workers
            else None
        ),
    }
    return {
        "worker_balance": worker_balance,
        "label": folder.name,
        "arguments": manifest["arguments"],
        "source_sha256": manifest["frozen_source_sha256"],
        "workload_sha256": manifest["workload_sha256"],
        "interrupted": (folder / "interrupted.json").exists(),
        "diagnostic": bool(manifest["arguments"].get("sample") or manifest["arguments"].get("cprofile")),
        "completed_workflows": values("completed_workflows"),
        "http_requests": values("http_reqs"),
        "acknowledged_booking_writes": values("acknowledged_booking_writes"),
        "workflow_latency_ms": values("workflow_duration_ms"),
        "successful_workflow_latency_ms": values("successful_workflow_duration_ms"),
        "http_latency_ms": values("http_req_duration"),
        "workflow_error_rate": values("workflow_errors"),
        "successful_workflow_count": complete,
        "failed_started_workflow_count": values("workflow_errors").get("passes", 0),
        "http_error_rate": values("http_req_failed"),
        "http_status_counts": dict(statuses),
        "offered_arrivals": attempts + dropped,
        "dropped_arrivals": dropped,
        "offered_not_completed_fraction": 1 - complete / (attempts + dropped) if attempts + dropped else None,
        "operations": {name: distribution(timings) for name, timings in operations.items()},
        "verification": verification,
        "durability": json.loads((folder / "durability.json").read_text()),
        "resource_window": {"start": samples[0]["utc"], "end": samples[-1]["utc"]},
        "api_cpu_seconds_sampling_window": api_cpu,
        "api_average_busy_logical_cpus": api_cpu / window_seconds if window_seconds else None,
        "api_cpu_utilisation_percent_of_host_logical_cpus": (
            100 * api_cpu / window_seconds / logical_cpus if window_seconds and logical_cpus else None
        ),
        "host_cpu_execution_utilisation_percent": host_cpu_utilisation,
        "host_logical_cpu_count": logical_cpus,
        "load_generator_cpu_seconds_sampling_window": load_cpu,
        "containers": containers,
        "application_cpu_ms_per_completed_workflow": total_app_cpu * 1000 / complete if complete and containers else None,
        "api_cpu_ms_per_completed_workflow": api_cpu * 1000 / complete if complete else None,
        "peak_observed_api_rss_mib": max(sum(p["rss_kib"] for p in row["processes"]) for row in samples) / 1024,
        "peak_sensor_temperatures_c": {name: max(temps) for name, temps in host_temperatures.items()},
        "limits": [
            "CPU counters cover the saved sampling window after warm-up through verification; "
            "sampling interval is two seconds.",
            "Aggregate API RSS counts shared pages repeatedly; cgroup memory includes charged page cache.",
            "Outbox published means broker-acknowledged; independent consumer and outage evidence is collected separately.",
            "Workflow wall latency uses Date.now() with one-millisecond clock resolution; "
            "HTTP timings are retained separately.",
            "Resource/setup changes require a fresh controlled comparison; failed offers are not successful throughput.",
            "CPU time per workflow is efficiency, not CPU utilisation. "
            "Host CPU utilisation also includes other host processes.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    arguments = parser.parse_args()
    result = report(arguments.folder)
    output = arguments.folder / "derived-metrics.json"
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(output)
