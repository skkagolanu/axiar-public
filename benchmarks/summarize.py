"""Generate comparisons from retained raw samples; never fill in missing results."""

import argparse
import json
import math
from pathlib import Path


def percentile(values, p):
    ordered = sorted(values)
    return ordered[math.ceil(len(ordered) * p) - 1]


def reduction(before, after):
    return (before - after) / before * 100 if before else None


def read(root, name):
    return json.loads((root / name).read_text())


def api(root):
    summaries = read(root, "api.json")
    result = {}
    for users in sorted({s["users"] for s in summaries}):
        repetitions = [s for s in summaries if s["users"] == users]
        samples, journey_samples = [], []
        for run in repetitions:
            raw = read(root, f'api-{users}-{run["repeat"]}-raw.json')
            samples.extend(raw["samples"])
            journey_samples.extend(raw["journey_ms"])
        elapsed = sum(s["elapsed_s"] for s in repetitions)
        errors = sum(s["errors"] for s in repetitions)
        operations = {}
        for name in sorted({s["operation"] for s in samples}):
            group = [s["ms"] for s in samples if s["operation"] == name]
            operations[name] = {"count": len(group), "p50_ms": percentile(group, 0.5), "p95_ms": percentile(group, 0.95)}
        result[users] = {
            "p50_ms": percentile([s["ms"] for s in samples], 0.5),
            "p95_ms": percentile([s["ms"] for s in samples], 0.95),
            "journey_p95_ms": percentile(journey_samples, 0.95),
            "requests_per_s": len(samples) / elapsed,
            "workflows_per_s": len(journey_samples) / elapsed,
            "errors": errors,
            "error_rate": errors / len(samples),
            "requests": len(samples),
            "operations": operations,
            "repetitions": repetitions,
        }
    return result


def compare(baseline, candidate):
    b, c = api(baseline), api(candidate)
    rows = []
    for users in sorted(b):
        assert users in c
        rows.append(
            {
                "users": users,
                "baseline": b[users],
                "candidate": c[users],
                "request_p95_reduction_pct": reduction(b[users]["p95_ms"], c[users]["p95_ms"]),
                "workflow_p95_reduction_pct": reduction(b[users]["journey_p95_ms"], c[users]["journey_p95_ms"]),
            }
        )
    database = {"baseline": read(baseline, "database.json"), "candidate": read(candidate, "database.json")}
    database["availability_p50_reduction_pct"] = reduction(
        database["baseline"]["availability"]["p50_ms"], database["candidate"]["availability"]["p50_ms"]
    )
    concurrency = {}
    for label, root in [("baseline", baseline), ("candidate", candidate)]:
        trials = read(root, "concurrency.json")
        concurrency[label] = {
            "rounds": len(trials),
            "attempts": sum(t["n"] for t in trials),
            "committed_conflicting_pairs": sum(t["conflicting_pairs"] for t in trials),
            "rounds_with_conflicts": sum(t["persisted"] > 1 for t in trials),
            "unexpected_failures": sum(
                int(count) for t in trials for status, count in t["statuses"].items() if status not in ("201", "409")
            ),
            "independent_adjacent_tenant_statuses": read(root, "concurrency-independent.json"),
            "trials": trials,
        }
    return {
        "baseline_directory": str(baseline),
        "candidate_directory": str(candidate),
        "api": rows,
        "database": database,
        "concurrency": concurrency,
        "events": {"baseline": read(baseline, "events.json"), "candidate": read(candidate, "events.json")},
    }


def markdown(report):
    lines = [
        "# Measured Axiar benchmark results",
        "",
        "All values below come from the saved manifests and raw JSON; see benchmarks/README.md for reproduction and limits.",
        "",
        "| Concurrent users | Request p95 baseline → candidate | Reduction | Workflow p95 baseline → candidate | Requests/sec baseline → candidate | Errors baseline / candidate |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in report["api"]:
        b, c = r["baseline"], r["candidate"]
        lines.append(
            f'| {r["users"]} | {b["p95_ms"]:.1f} → {c["p95_ms"]:.1f} ms | {r["request_p95_reduction_pct"]:.1f}% | '
            f'{b["journey_p95_ms"]:.1f} → {c["journey_p95_ms"]:.1f} ms | {b["requests_per_s"]:.1f} → {c["requests_per_s"]:.1f} | {b["errors"]} / {c["errors"]} |'
        )
    db = report["database"]
    lines += [
        "",
        f'Availability check p50: {db["baseline"]["availability"]["p50_ms"]:.3f} → '
        f'{db["candidate"]["availability"]["p50_ms"]:.3f} ms ({db["availability_p50_reduction_pct"]:.1f}% reduction).',
        "",
    ]
    for label in ["baseline", "candidate"]:
        concurrency = report["concurrency"][label]
        events = report["events"][label]
        cache = db[label]["tenant_cache"]
        lines += [
            f'**{label}:** {concurrency["attempts"]} booking attempts across {concurrency["rounds"]} rounds; '
            f'{concurrency["committed_conflicting_pairs"]} conflicting persisted pairs; '
            f'{concurrency["unexpected_failures"]} unexpected transaction/HTTP failures.',
            "",
            f'Healthy events: {events["healthy"]}. Cold-start outage: {events["cold_start_outage"]}.',
            "",
            f'Tenant-resolution Redis cache: {cache["hits"]} hits / {cache["misses"]} misses; '
            f'cold p50 {cache["cold_ms"]["p50_ms"]:.3f} ms; warm p50 {cache["warm_ms"]["p50_ms"]:.3f} ms.',
            "",
        ]
    lines += [
        "These are finite local synthetic experiments with one API worker, 100,000 all-active synthetic bookings, real isolated services, disabled rate limiting, three short HTTP repetitions, and sequential baseline/candidate order. Component cache gains refer to the existing tenant cache, not a new booking cache. Delivery is at least once; consumer business-effect idempotency and production capacity were not established.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/results/comparison.json"))
    args = parser.parse_args()
    report = compare(args.baseline, args.candidate)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(markdown(report))
    print(markdown(report))
