"""HTTP cancellation/rebooking and tenant/object-authorization probes on seeded data."""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import httpx
from environment import API_URL, environment

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--source", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--expect-fixed", action="store_true")
args = parser.parse_args()
os.environ.update(environment())
sys.path.insert(0, str(args.source.resolve() / "backend"))

from app.core.security import security_manager


def uid(value):
    return str(uuid5(NAMESPACE_URL, f"axiar-benchmark-v1/{value}"))


def headers(t, p, kind="customer"):
    token = security_manager.create_access_token(
        {"sub": uid(f"{kind}/{t}/{p}")}, expires_delta=timedelta(hours=1), extra_claims={"tenant_id": uid(f"tenant/{t}")}
    )
    return {"Authorization": f"Bearer {token}", "X-Tenant-ID": uid(f"tenant/{t}")}


async def main():
    env = environment()
    env["PYTHONPATH"] = str(args.source.resolve() / "backend")
    with args.output.with_suffix(".log").open("w") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "58089", "--no-access-log"],
            cwd=args.source / "backend",
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            async with httpx.AsyncClient(base_url=API_URL, timeout=30) as client:
                for _ in range(120):
                    if process.poll() is not None:
                        raise RuntimeError("API exited")
                    try:
                        if (await client.get("/api/v1/health")).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(0.5)
                else:
                    raise RuntimeError("API failed to start")
                payload = {
                    "provider_id": uid("provider/0/20"),
                    "service_id": uid("service/0/20"),
                    "scheduled_time": datetime(2200, 1, 1, tzinfo=timezone.utc).isoformat(),
                    "duration_minutes": 60,
                    "base_price_cents": 5000,
                    "location_postcode": "NG7 2RD",
                    "description": "benchmark-correctness",
                }
                created = await client.post("/api/v1/bookings/", headers=headers(0, 0), json=payload)
                assert created.status_code == 201, created.text
                bid = created.json()["id"]
                same_tenant_other_customer = await client.get(f"/api/v1/bookings/{bid}", headers=headers(0, 1))
                other_tenant = await client.get(f"/api/v1/bookings/{bid}", headers=headers(1, 0))
                wrong_tenant_header = headers(0, 0)
                wrong_tenant_header["X-Tenant-ID"] = uid("tenant/1")
                mismatch = await client.get(f"/api/v1/bookings/{bid}", headers=wrong_tenant_header)
                confirmed = await client.patch(
                    f"/api/v1/bookings/{bid}/status", headers=headers(0, 20, "provider-user"), json={"status": "confirmed"}
                )
                cancelled = await client.patch(
                    f"/api/v1/bookings/{bid}/status", headers=headers(0, 0), json={"status": "cancelled"}
                )
                rebooked = await client.post("/api/v1/bookings/", headers=headers(0, 0), json=payload)
                cross_payload = {
                    **payload,
                    "provider_id": uid("provider/1/20"),
                    "service_id": uid("service/1/20"),
                    "scheduled_time": datetime(2200, 1, 2, tzinfo=timezone.utc).isoformat(),
                }
                cross_create = await client.post("/api/v1/bookings/", headers=headers(0, 0), json=cross_payload)
                result = {
                    "create": created.status_code,
                    "confirm_by_profile_owner": confirmed.status_code,
                    "cancel": cancelled.status_code,
                    "rebook_cancelled_slot": rebooked.status_code,
                    "other_customer_read": same_tenant_other_customer.status_code,
                    "other_tenant_read": other_tenant.status_code,
                    "mismatched_token_tenant_header": mismatch.status_code,
                    "cross_tenant_provider_service_create": cross_create.status_code,
                }
                args.output.write_text(json.dumps(result, indent=2) + "\n")
                print(json.dumps(result), flush=True)
                if args.expect_fixed:
                    assert result == {
                        "create": 201,
                        "confirm_by_profile_owner": 200,
                        "cancel": 200,
                        "rebook_cancelled_slot": 201,
                        "other_customer_read": 403,
                        "other_tenant_read": 404,
                        "mismatched_token_tenant_header": 401,
                        "cross_tenant_provider_service_create": 404,
                    }, result
        finally:
            process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


asyncio.run(main())
