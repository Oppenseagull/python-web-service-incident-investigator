"""Real TCP services and a Registry attached to the observed app process."""

import asyncio
import json
import os
import socket
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
import uvicorn

from app.config import Settings
from app.main import create_app
from downstream.main import DownstreamSettings, create_app as create_dependency
from scripts.reproduce_db_pool_exhaustion import reproduce as reproduce_db
from scripts.reproduce_downstream_timeout import reproduce as reproduce_http


@asynccontextmanager
async def serve(app):
    """One real server in this process so Python tools see the correct cache/pool."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    sock.setblocking(False)
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", lifespan="on"))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if task.done():
                    await task
                    raise RuntimeError("Server failed before readiness")
                await asyncio.sleep(0.01)
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(task, timeout=10)
        finally:
            sock.close()


async def safe_fault_results(app, records, expected_code):
    registry = app.state.investigator_tools
    outputs = []
    for record in records:
        result = await registry.execute({"tool_name": "get_recent_app_events",
                                         "arguments": {"request_id": record["request_id"]}})
        assert result.status == "ok" and len(result.observations) == 1
        event = result.observations[0]
        assert registry.get_evidence(event.evidence_id) == event
        assert event.data.status_code == record["observations"]["status_code"]
        outputs.append(result)
    fault = outputs[1].observations[0]
    assert fault.data.error_type == expected_code
    assert fault.data.latency_ms >= 800
    health = await registry.execute({"tool_name": "check_downstream_health"})
    assert health.status == "ok" and health.observations[0].data.status_code == 200
    snapshot = await registry.execute({"tool_name": "get_db_pool_snapshot"})
    assert snapshot.status == "ok" and snapshot.observations[0].data.checked_out == 0
    outputs.extend([health, snapshot])
    recent = await registry.execute({"tool_name": "get_recent_app_events", "arguments": {
        "start_time": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
        "end_time": datetime.now(timezone.utc).isoformat(), "limit": 50,
    }})
    encoded = recent.model_dump_json()
    for forbidden in ("scenario_id", "incident_id", "db-pool-exhaustion", "downstream-http-timeout",
                      "fault_active", "delay_seconds", "remaining_seconds", "/lab/", "held_seconds"):
        assert forbidden not in encoded
    return outputs


def export_results(tmp_path, name, results):
    run_dir = Path(os.getenv("S1_RUN_DIR", str(tmp_path)))
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / name).write_text(json.dumps([r.model_dump(mode="json") for r in results], indent=2)
                                + "\n", encoding="utf-8")
    fault = results[1].observations[0]
    print(f"S1 real tools: statuses={[r.observations[0].data.status_code for r in results[:3]]} "
          f"error={fault.data.error_type} latency_ms={fault.data.latency_ms} "
          f"request_id={fault.request_id} evidence_id={fault.evidence_id}; "
          "health=200; control metadata excluded")


@pytest.mark.http_integration
def test_tools_observe_real_http_timeout_and_recovery(tmp_path):
    async def scenario():
        dependency = create_dependency(DownstreamSettings(_env_file=None, fault_lab_enabled=True))
        async with serve(dependency) as downstream_url:
            app = create_app(Settings(_env_file=None, postgres_password="unused-http-only-test",
                                     postgres_port=1, fault_lab_enabled=True,
                                     downstream_base_url=downstream_url))
            async with serve(app) as app_url, httpx.AsyncClient(base_url=app_url, timeout=15,
                                                               trust_env=False) as client, \
                    httpx.AsyncClient(base_url=downstream_url, timeout=15, trust_env=False) as control:
                records = await reproduce_http(client, control, emit=lambda line: None)
                results = await safe_fault_results(app, records, "DOWNSTREAM_HTTP_TIMEOUT")
                fault = results[1].observations[0]
                assert fault.data.exception_class == "ReadTimeout"
                assert fault.data.dependency == "controlled-http"
                assert fault.data.dependency_latency_ms >= 800
                assert results[-1].observations[0].data.checked_in == 0  # never opened a DB connection
                export_results(tmp_path, "safe-http-evidence.json", results)
    asyncio.run(scenario())


@pytest.mark.integration
@pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="Requires real PostgreSQL")
def test_tools_observe_real_postgres_pool_timeout_and_recovery(tmp_path):
    async def scenario():
        app = create_app(Settings(fault_lab_enabled=True))
        async with serve(app) as app_url, httpx.AsyncClient(base_url=app_url, timeout=15,
                                                          trust_env=False) as client:
            records = await reproduce_db(client, emit=lambda line: None)
            results = await safe_fault_results(app, records, "DB_POOL_TIMEOUT")
            fault = results[1].observations[0]
            assert fault.data.db_pool.checked_out == 2 and fault.data.db_pool.checked_in == 0
            assert results[-1].observations[0].data.checked_in == 2
            export_results(tmp_path, "safe-db-evidence.json", results)
    asyncio.run(scenario())
