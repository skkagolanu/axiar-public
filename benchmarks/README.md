# Booking workload

Run the tools only against the dedicated local synthetic environment. They reset
their own benchmark database. Install `benchmarks/requirements.lock` in a dedicated virtual environment
and install k6 separately.

`environment.py` manages the loopback-only PostgreSQL, Redis and Kafka services.
`sustain.py` drives the five-request scheduling/create/confirm/read/cancel workflow.
`transactions.py`, `correctness.py`, `kafka_audit.py` and `outage_workflows.py`
provide separate consistency and delivery checks. Use each script's `--help`
before an explicitly requested run.

```sh
python benchmarks/environment.py up
python benchmarks/sustain.py --source . --label local-check --help
python benchmarks/environment.py down
```

For a before/after campaign, supply two source directories with
`campaign.py --label comparison --baseline PATH` from the candidate directory.

`reference_results.json` contains the load measurements and broker reconciliation.
`availability_results.json` contains repository latency samples, SQL and query
plans for the two-tenant, 100,000-booking comparison. Percentiles use nearest-rank
ordering. Run `python benchmarks/verify_results.py` to check the saved evidence.

One booking workflow comprises five authenticated HTTP requests and three
committed writes. Load-test results report HTTP requests/s and complete
workflows/s separately. Availability latency measures repository wall time.
