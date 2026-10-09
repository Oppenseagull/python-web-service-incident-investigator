"""Reproduce M0 against a dedicated, idle, single-worker lab instance."""

import argparse
import asyncio
import json
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path

import httpx

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.evidence import Evidence


def require(condition: bool, message: str) -> None:
    # Unlike assert, this check also runs under python -O.
    if not condition:
        raise RuntimeError(message)


async def reproduce(client: httpx.AsyncClient, emit: Callable[[str], None] = print) -> list[dict]:
    incident_id = uuid.uuid4().hex
    records: list[dict] = []

    def record(phase: str, response: httpx.Response, elapsed_ms: float, pool: dict) -> None:
        evidence = Evidence(
            source="reproduction", event_type="scenario_observation",
            incident_id=incident_id, scenario_id="db-pool-exhaustion",
            request_id=response.headers.get("x-request-id"), dependency="postgres",
            error_type=response.json().get("error", {}).get("code"), latency_ms=elapsed_ms,
            observations={"phase": phase, "status_code": response.status_code,
                          "body": response.json(), "db_pool": pool},
        ).model_dump(mode="json")
        records.append(evidence)
        emit("evidence=" + json.dumps(evidence))

    health = await client.get("/healthz")
    require(health.status_code == 200, f"Health check failed: {health.status_code}")
    normal_start = time.perf_counter()
    normal = await client.get("/items/1")
    normal_ms = (time.perf_counter() - normal_start) * 1000
    require(normal.status_code == 200, f"Normal request failed: {normal.status_code}")
    require(normal.json().get("id") == 1, "Normal request did not return item 1")
    emit(f"normal: {normal.status_code} {normal.json()}")

    async def state() -> dict[str, int | float]:
        response = await client.get("/lab/diagnostics/db-pool")
        require(response.status_code == 200, "Diagnostics unavailable; enable FAULT_LAB_ENABLED")
        return response.json()

    initial = await state()
    require(
        initial["configured_pool_size"] == 2
        and initial["configured_max_overflow"] == 0
        and initial["pool_timeout_seconds"] == 1,
        "This reproduction requires lab defaults: size=2, overflow=0, timeout=1",
    )
    require(initial["checked_out"] == 0, "Use an idle lab without other DB requests")
    emit(f"before: {json.dumps(initial)}")
    record("normal", normal, normal_ms, initial)

    started = time.perf_counter()
    holds = [asyncio.create_task(client.post(
        "/lab/faults/db-pool/hold", json={"hold_seconds": 5}, timeout=15,
    )) for _ in range(2)]
    try:
        deadline = started + 2
        while True:
            require(not any(task.done() for task in holds), "A hold request ended before occupancy")
            occupied = await state()
            require(time.perf_counter() < deadline, "Connections not occupied within 2 seconds")
            if occupied["checked_out"] == 2 and occupied["checked_in"] == 0:
                break
            await asyncio.sleep(0.02)  # Poll interval, not the readiness condition.
        emit(f"occupied: {json.dumps(occupied)}")
        require((await client.get("/healthz")).status_code == 200, "Liveness failed during fault")
        begin = time.perf_counter()
        failed = await client.get("/items/1")
        elapsed = time.perf_counter() - begin
        emit(f"fault: status={failed.status_code} latency_ms={elapsed * 1000:.2f} "
             f"request_id={failed.headers.get('x-request-id')} body={failed.text}")
        require(failed.status_code == 503, f"Expected 503, got {failed.status_code}")
        require(failed.json() == {"error": {
            "code": "DB_POOL_TIMEOUT",
            "message": "Database connection pool temporarily exhausted",
        }}, "Unexpected timeout error body")
        require(0.8 <= elapsed < 2.5, f"Unexpected pool timeout duration: {elapsed:.3f}s")
        require(bool(failed.headers.get("x-request-id")), "Missing request ID")
        record("fault", failed, elapsed * 1000, occupied)
    finally:
        # Let the server release both sessions, including if an assertion fails.
        results = await asyncio.gather(*holds, return_exceptions=True)
    for result in results:
        if isinstance(result, BaseException):
            raise RuntimeError("Hold request failed") from result
        require(result.status_code == 200, f"Hold request failed: {result.status_code}")
    recovery_start = time.perf_counter()
    recovered = await client.get("/items/1")
    recovery_ms = (time.perf_counter() - recovery_start) * 1000
    require(recovered.status_code == 200, f"Recovery failed: {recovered.status_code}")
    require(recovered.json() == normal.json(), "Recovered item differs from baseline")
    final = await state()
    require(final["checked_out"] == 0, "Connections were not returned after recovery")
    emit(f"recovered: {recovered.status_code}; after: {json.dumps(final)}")
    record("recovered", recovered, recovery_ms, final)
    emit("PASS: real pool exhaustion produced structured 503, then recovered")
    return records


async def main(base_url: str, output: Path | None = None) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=15, trust_env=False) as client:
        records = await reproduce(client)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        asyncio.run(main(args.base_url, args.output))
    except (RuntimeError, httpx.HTTPError, ValueError, KeyError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
