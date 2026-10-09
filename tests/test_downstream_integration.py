"""Real TCP/HTTP integration, independent of Docker/PostgreSQL availability."""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from app.evidence import Evidence
from scripts.reproduce_downstream_timeout import reproduce

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.http_integration


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def real_http_lab(tmp_path):
    run_dir = Path(os.getenv("LAB_RUN_DIR", str(tmp_path)))
    run_dir.mkdir(parents=True, exist_ok=True)
    processes: list[subprocess.Popen] = []
    streams = []
    downstream_port = free_port()
    app_port = free_port()
    downstream_url = f"http://127.0.0.1:{downstream_port}"
    app_url = f"http://127.0.0.1:{app_port}"
    env = {**os.environ, "FAULT_LAB_ENABLED": "true",
           "POSTGRES_PASSWORD": "unused-http-only-test", "POSTGRES_HOST": "127.0.0.1",
           "POSTGRES_PORT": "1", "DB_POOL_SIZE": "2", "DB_MAX_OVERFLOW": "0",
           "DB_POOL_TIMEOUT": "1", "DOWNSTREAM_BASE_URL": downstream_url,
           "DOWNSTREAM_READ_TIMEOUT": "1"}
    try:
        for name, port in (("downstream", downstream_port), ("app", app_port)):
            stream = (run_dir / f"{name}.log").open("w", encoding="utf-8")
            streams.append(stream)
            processes.append(subprocess.Popen(
                [sys.executable, "-m", "uvicorn", f"{name}.main:create_app", "--factory",
                 "--host", "127.0.0.1", "--port", str(port), "--workers", "1",
                 "--log-config", "app/logging.json"],
                cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            ))
        with httpx.Client(timeout=0.5, trust_env=False) as client:
            deadline = time.perf_counter() + 20
            for url in (downstream_url, app_url):
                while True:
                    if any(process.poll() is not None for process in processes):
                        raise RuntimeError(f"HTTP process exited; inspect {run_dir}")
                    try:
                        if client.get(url + "/healthz").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    if time.perf_counter() > deadline:
                        raise RuntimeError(f"HTTP process readiness failed; inspect {run_dir}")
                    time.sleep(0.02)
        yield app_url, downstream_url, run_dir
    finally:
        for process in reversed(processes):
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for stream in streams:
            stream.close()


def test_real_http_timeout_recovery_and_correlated_evidence(real_http_lab) -> None:
    app_url, downstream_url, run_dir = real_http_lab

    async def scenario() -> list[dict]:
        async with httpx.AsyncClient(base_url=app_url, timeout=15, trust_env=False) as client, \
                httpx.AsyncClient(base_url=downstream_url, timeout=15, trust_env=False) as dependency:
            return await reproduce(client, dependency)

    records = asyncio.run(scenario())
    (run_dir / "scenario.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    assert [r["observations"]["status_code"] for r in records] == [200, 504, 200]
    for record in records:
        Evidence.model_validate(record)
    log_records = [Evidence.model_validate_json(line.split("evidence=", 1)[1])
                   for line in (run_dir / "app.log").read_text(encoding="utf-8").splitlines()
                   if "evidence=" in line]
    fault = next(r for r in log_records if r.error_type == "DOWNSTREAM_HTTP_TIMEOUT")
    assert fault.request_id == records[1]["request_id"]
    assert fault.dependency == "controlled-http"
    assert fault.scenario_id == "downstream-http-timeout"
    assert fault.observations["exception_class"] == "ReadTimeout"
    assert fault.observations["dependency_latency_ms"] >= 800
    assert "DB_POOL_TIMEOUT" not in (run_dir / "app.log").read_text(encoding="utf-8")
    assert f"dependency_received request_id={fault.request_id} applied_delay_seconds=3.0" in (
        run_dir / "downstream.log").read_text(encoding="utf-8")
