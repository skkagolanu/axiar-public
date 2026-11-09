"""Check retained results without starting services or generating load."""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def main():
    availability = json.loads((ROOT / "availability_results.json").read_text())
    for config in availability["configurations"].values():
        samples = sorted(config["availability_raw_ms"])
        assert len(samples) == config["availability"]["count"] == 30
        for quantile, key in [(0.5, "p50_ms"), (0.95, "p95_ms")]:
            assert math.isclose(samples[math.ceil(len(samples) * quantile) - 1], config["availability"][key])
    reference = json.loads((ROOT / "reference_results.json").read_text())
    for run in reference["runs"]:
        metric = run["k6_metrics"]
        completed = metric["completed_workflows"]["values"]["count"]
        assert metric["http_reqs"]["values"]["count"] == completed * 5
        assert run["verification"]["persisted_completed_workflows"] == completed
        assert run["kafka"]["expected_committed_outbox_events"] == completed * 3
        assert run["kafka"]["independently_observed_outbox_ids"] == completed * 3
        assert run["missing_events"] == 0
        assert run["kafka"]["duplicate_deliveries_of_expected_ids"] == 0
        assert not metric["workflow_duration_ms"]["thresholds"]["p(99)<10"]["ok"]
    assert reference["runs"][1]["k6_metrics"]["dropped_iterations"]["values"]["count"] == 129
    print("Availability samples, workflow accounting, event reconciliation and failed thresholds are consistent.")

if __name__ == "__main__":
    main()
