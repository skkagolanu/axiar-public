"""Independently read the real Kafka log after a load run, without load-time observer overhead."""

import argparse
import asyncio
import gzip
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

import asyncpg
from aiokafka import AIOKafkaConsumer, TopicPartition
from environment import BROKER, DB_URL


async def audit(folder):
    manifest = json.loads((folder / "manifest.json").read_text())
    verified = json.loads((folder / "verification.json").read_text())
    conn = await asyncpg.connect(DB_URL.replace("postgresql+asyncpg", "postgresql"))
    try:
        rows = await conn.fetch("""
            SELECT o.id,o.aggregate_id,o.event_type,o.tenant_id,b.status
            FROM outbox_messages o JOIN bookings b ON b.id=o.aggregate_id
            WHERE b.description='benchmark-extremes'
        """)
    finally:
        await conn.close()
    expected = {str(row["id"]): (str(row["aggregate_id"]), row["event_type"], str(row["tenant_id"])) for row in rows}
    aggregates = {row[0] for row in expected.values()}
    assert len(aggregates) == verified["persisted_completed_workflows"], "Run only before the next fixture reset"
    # Verify membership against every saved client acknowledgement, not merely a count.
    acknowledged = set()
    with gzip.open(folder / "raw.ndjson.gz", "rt") as stream:
        for line in stream:
            if '"completed_workflows"' in line:
                point = json.loads(line)
                if point.get("metric") == "completed_workflows" and point.get("type") == "Point":
                    acknowledged.add(point["data"]["metadata"]["booking_id"])
    assert acknowledged <= aggregates, "The current database does not belong to this run"
    topic = "axiar.booking.events"
    consumer = AIOKafkaConsumer(topic, bootstrap_servers=BROKER, group_id=None, enable_auto_commit=False)
    await consumer.start()
    observed_ids = Counter()
    logical_events = Counter()
    invalid_payloads = 0
    try:
        # Subscribing before start waits for this topic's metadata. topics()
        # alone returns a separate metadata snapshot, not the consumer's cache.
        partitions = [TopicPartition(topic, p) for p in sorted(consumer.partitions_for_topic(topic) or [])]
        assert partitions, "Booking topic is missing"
        timestamp_ms = int(datetime.fromisoformat(manifest["utc"]).timestamp() * 1000)
        offsets = await consumer.offsets_for_times({p: timestamp_ms for p in partitions})
        ends = await consumer.end_offsets(partitions)
        consumer.unsubscribe()
        consumer.assign(partitions)
        for partition in partitions:
            consumer.seek(partition, offsets[partition].offset if offsets[partition] else ends[partition])
        offset_manifest = {
            f"{p.topic}:{p.partition}": {"start": offsets[p].offset if offsets[p] else ends[p], "end": ends[p]}
            for p in partitions
        }
        with gzip.open(folder / "kafka-observed.ndjson.gz", "wt") as ledger:
            async with asyncio.timeout(180):
                while True:
                    batch = await consumer.getmany(timeout_ms=250, max_records=5000)
                    for partition, messages in batch.items():
                        for message in messages:
                            if message.offset >= ends[partition]:
                                continue
                            payload = json.loads(message.value)
                            aggregate = str(payload.get("aggregate_id"))
                            if aggregate not in aggregates:
                                continue
                            event_id = str(payload.get("event_id"))
                            key = (aggregate, payload.get("event_type"), str(payload.get("tenant_id")))
                            observed_ids[event_id] += 1
                            logical_events[key] += 1
                            if event_id in expected and key != expected[event_id]:
                                invalid_payloads += 1
                            ledger.write(
                                json.dumps({"partition": partition.partition, "offset": message.offset, "payload": payload})
                                + "\n"
                            )
                    if all([await consumer.position(p) >= ends[p] for p in partitions]):
                        break
    finally:
        await consumer.stop()
    missing = sorted(set(expected) - set(observed_ids))
    result = {
        "expected_committed_outbox_events": len(expected),
        "independently_observed_outbox_ids": len(set(expected) & set(observed_ids)),
        "missing_outbox_ids": missing,
        "duplicate_deliveries_of_expected_ids": sum(max(0, observed_ids[eid] - 1) for eid in expected),
        "semantic_duplicate_messages": sum(max(0, count - 1) for count in logical_events.values()),
        "observed_messages_for_measured_bookings": sum(observed_ids.values()),
        "payload_or_tenant_mismatches": invalid_payloads,
        "offset_window": offset_manifest,
        "scope": "Independent broker-log read after warmup/load, bounded by captured end offsets; not exactly-once consumer effects.",
    }
    (folder / "kafka-audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "missing_outbox_ids"}), flush=True)
    assert not missing and invalid_payloads == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    asyncio.run(audit(args.folder))
