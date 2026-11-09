"""Summarize every strict-workflow experiment, including failures and profiling runs."""

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT/'benchmarks/results'
rows = []
for folder in RESULTS.iterdir():
    manifest_file,summary_file = folder/'manifest.json',folder/'k6-summary.json'
    if not manifest_file.exists() or not summary_file.exists():
        continue
    manifest = json.loads(manifest_file.read_text())
    if 'expected_write_tps' not in manifest:
        continue
    metrics = json.loads(summary_file.read_text())['metrics']
    def value(name,field):
        return metrics.get(name,{}).get('values',{}).get(field)
    verification_file = folder/'verification.json'
    verified = json.loads(verification_file.read_text()) if verification_file.exists() else {}
    arguments = manifest['arguments']
    count = value('completed_workflows','count')
    attempted = value('workflow_attempts','count')
    dropped = value('dropped_iterations','count')
    offered_count = attempted+dropped if attempted is not None and dropped is not None else None
    cpu_seconds = None
    resources = folder/'resources.ndjson'
    if resources.exists():
        samples = [json.loads(line) for line in resources.read_text().splitlines() if line.strip()]
        if len(samples)>1:
            first = {p['pid']:p['cpu_s'] for p in samples[0]['processes']}
            cpu_seconds = sum(p['cpu_s']-first.get(p['pid'],p['cpu_s']) for p in samples[-1]['processes'])
    rows.append({
        'label':folder.name,'utc':manifest['utc'],'workers':arguments['workers'],'pool':arguments['pool'],
        'db_cpus':arguments['db_cpus'],'offered_wps':arguments['rate'],'duration':arguments['duration'],
        'diagnostic_profile':bool(arguments.get('sample') or arguments.get('cprofile')),
        'achieved_wps':value('completed_workflows','rate'),'completed_workflows':count,
        'http_rps':value('http_reqs','rate'),'workflow_p50_ms':value('workflow_duration_ms','p(50)'),
        'workflow_p95_ms':value('workflow_duration_ms','p(95)'),'workflow_p99_ms':value('workflow_duration_ms','p(99)'),
        'error_rate':value('workflow_errors','rate'),'dropped_arrivals':value('dropped_iterations','count'),
        'offered_workflows_not_completed_fraction':1-count/offered_count if offered_count and count is not None else None,
        'individually_verified_ids':verified.get('individually_verified_acknowledged_ids'),
        'persisted_cancelled':verified.get('persisted_completed_workflows'),
        'overlaps':verified.get('overlapping_active_intervals'),'tenant_reference_errors':verified.get('cross_tenant_references'),
        'unacknowledged_cancellations':verified.get('committed_cancellations_without_client_success'),
        'cpu_seconds_sampling_window':cpu_seconds,
        'cpu_ms_per_completed_workflow':cpu_seconds*1000/count if cpu_seconds is not None and count else None,
        'source_sha256':manifest.get('frozen_source_sha256'),
    })
rows.sort(key=lambda row:row['utc'])
(RESULTS/'tuning.json').write_text(json.dumps({'experiments':rows},indent=2)+'\n')
lines = ['# Strict workflow tuning results','',
         'One transaction here means the complete five-request, three-write workflow. Short experiments guide tuning; they are not sustained-capacity claims. Profiling runs are diagnostic and cannot support before/after latency claims. All outcomes are retained.','',
         '| Experiment | Workers / pool each / DB CPU | Offered → completed workflows/sec | Workflow p99 | Started-workflow errors | Dropped | Offered not completed | Individual ID verification | Profiled |',
         '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']
for row in rows:
    fmt = lambda v: 'unknown' if v is None else f'{v:.2f}'
    ids = row['individually_verified_ids']
    uncompleted = row['offered_workflows_not_completed_fraction']
    lines.append(f"| {row['label']} | {row['workers']} / {row['pool']} / {row['db_cpus']} | {row['offered_wps']} → {fmt(row['achieved_wps'])} | {fmt(row['workflow_p99_ms'])} ms | {fmt(row['error_rate']*100 if row['error_rate'] is not None else None)}% | {row['dropped_arrivals']} | {fmt(uncompleted*100 if uncompleted is not None else None)}% | {ids if ids is not None else 'count-only'} | {row['diagnostic_profile']} |")
lines += ['', 'The original target remains **500 complete workflows/sec with workflow p99 <10 ms**. No run is labelled a success merely because 500 HTTP RPS was offered. Database durability settings and resource changes are saved per experiment. Counts include committed cancellations without successful client acknowledgement separately; those do not count as completed throughput. All newer successful-workflow IDs are reconciled against their persisted state and tenant.',
          '', 'CPU figures in tuning.json cover the sampled process window and include background event-relay work. Scaling worker or database CPU allocation is a resource change, not a same-resource efficiency achievement.', '']
(ROOT/'benchmarks/tuning-results.md').write_text('\n'.join(lines))
print('\n'.join(lines))
