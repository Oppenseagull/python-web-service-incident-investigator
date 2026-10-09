"""Real HTTP normal -> controlled response delay -> read timeout -> recovery."""

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path

import httpx

# Running as `python scripts/...` must also find the application contract.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.evidence import Evidence
from scripts.reproduce_db_pool_exhaustion import require


async def reproduce(
    client: httpx.AsyncClient, downstream: httpx.AsyncClient,
    emit: Callable[[str], None] = print,
) -> list[dict]:
    incident_id = uuid.uuid4().hex
    records: list[dict] = []

    async def diagnostic() -> dict:
        response = await downstream.get("/lab/diagnostics/state")
        require(response.status_code == 200, "Enable FAULT_LAB_ENABLED on the downstream")
        return response.json()

    async def pool_state() -> dict:
        response = await client.get("/lab/diagnostics/db-pool")
        require(response.status_code == 200, "Enable FAULT_LAB_ENABLED on the app")
        return response.json()

    async def read_value(phase: str) -> httpx.Response:
        start = time.perf_counter()
        response = await client.get("/downstream/value")
        elapsed = (time.perf_counter() - start) * 1000
        require(bool(response.headers.get("x-request-id")), "Missing request ID")
        record = Evidence(
            source="reproduction", event_type="scenario_observation",
            incident_id=incident_id, scenario_id="downstream-http-timeout",
            request_id=response.headers["x-request-id"], dependency="controlled-http",
            error_type=response.json().get("error", {}).get("code"), latency_ms=elapsed,
            observations={"phase": phase, "status_code": response.status_code,
                          "body": response.json(), "db_pool": await pool_state(),
                          "downstream_state": await diagnostic()},
        ).model_dump(mode="json")
        records.append(record)
        emit(json.dumps(record))
        return response

    for name, target in (("app", client), ("downstream", downstream)):
        require((await target.get("/healthz")).status_code == 200, f"{name} health failed")
    config = await client.get("/lab/diagnostics/downstream")
    require(config.status_code == 200, "App downstream diagnostics unavailable")
    timeout = config.json()["read_timeout_seconds"]
    require(timeout == 1, "This reproduction requires DOWNSTREAM_READ_TIMEOUT=1")
    initial = await diagnostic()
    require(not initial["fault_active"] and initial["active_requests"] == 0,
            "Use an idle dependency without an existing delay fault")
    initial_pool = await pool_state()
    require(initial_pool["checked_out"] == 0, "Use an idle app DB pool")
    baseline = await read_value("normal")
    require(baseline.status_code == 200 and baseline.json() == {"value": "ready"},
            "Normal downstream request failed")

    try:
        injected = await downstream.post("/lab/faults/response-delay", json={
            "delay_seconds": 3, "duration_seconds": 10,
        })
        require(injected.status_code == 200, "Delay injection failed")
        # Read state after the mutation completes; no arbitrary readiness sleep.
        active = await diagnostic()
        require(active["fault_active"] and active["delay_seconds"] == 3
                and active["remaining_seconds"] > 3, "Delay fault was not armed")
        failed = await read_value("fault")
        require(failed.status_code == 504, f"Expected 504, got {failed.status_code}")
        require(failed.json() == {"error": {
            "code": "DOWNSTREAM_HTTP_TIMEOUT",
            "message": "Downstream response exceeded read timeout",
        }}, "Unexpected timeout body")
        fault = records[-1]
        require(800 <= fault["latency_ms"] < 2500, "Unexpected read timeout latency")
        observed = fault["observations"]
        require(observed["db_pool"] == initial_pool, "DB pool changed during HTTP-only scenario")
        require(observed["downstream_state"]["last_request_id"] == fault["request_id"],
                "Dependency did not observe the correlated request")
        require(observed["downstream_state"]["active_requests"] == 1,
                "Dependency is not still serving the timed-out request")
        require((await client.get("/healthz")).status_code == 200, "App liveness failed")
    finally:
        # Reset even after failed assertions. A TTL also bounds abandoned faults.
        reset = await downstream.delete("/lab/faults/response-delay")
        require(reset.status_code == 200, "Failed to reset delay fault")
        # Already-started requests retain their snapshot delay; wait for cleanup.
        deadline = time.perf_counter() + 5
        while (await diagnostic())["active_requests"]:
            require(time.perf_counter() < deadline, "Dependency requests did not drain")
            await asyncio.sleep(0.02)
    recovered = await read_value("recovered")
    require(recovered.status_code == 200 and recovered.json() == baseline.json(), "Recovery failed")
    require(not records[-1]["observations"]["downstream_state"]["fault_active"],
            "Delay fault remained active after reset")
    emit("PASS: real downstream read timeout produced structured 504, then recovered")
    return records


async def main(base_url: str, downstream_url: str, output: Path | None) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=15, trust_env=False) as client, \
            httpx.AsyncClient(base_url=downstream_url, timeout=15, trust_env=False) as downstream:
        records = await reproduce(client, downstream)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--downstream-url", default=os.getenv("DOWNSTREAM_BASE_URL", "http://127.0.0.1:8001"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        asyncio.run(main(args.base_url, args.downstream_url, args.output))
    except (RuntimeError, httpx.HTTPError, ValueError, KeyError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
