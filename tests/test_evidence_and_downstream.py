import asyncio
import json
import logging

import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.evidence import Evidence
from app.main import create_app
from downstream.main import DownstreamSettings, create_app as create_dependency


def test_delay_requires_flag_and_validates_bounds_and_expires() -> None:
    async def scenario() -> None:
        disabled = create_dependency(DownstreamSettings(_env_file=None, fault_lab_enabled=False))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=disabled), base_url="http://test") as client:
            assert (await client.get("/value")).json() == {"value": "ready"}
            assert (await client.post("/lab/faults/response-delay", json={
                "delay_seconds": 3, "duration_seconds": 10,
            })).status_code == 404
            assert (await client.delete("/lab/faults/response-delay")).status_code == 404
            assert (await client.get("/lab/diagnostics/state")).status_code == 404
        enabled = create_dependency(DownstreamSettings(_env_file=None, fault_lab_enabled=True))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=enabled), base_url="http://test") as client:
            for body in ({"delay_seconds": -1}, {"delay_seconds": 11},
                         {"delay_seconds": 1, "duration_seconds": 0},
                         {"delay_seconds": 1, "duration_seconds": 61}):
                assert (await client.post("/lab/faults/response-delay", json=body)).status_code == 422
            assert (await client.post("/lab/faults/response-delay", json={
                "delay_seconds": 0.1, "duration_seconds": 0.03,
            })).status_code == 200
            await asyncio.sleep(0.06)
            state = (await client.get("/lab/diagnostics/state")).json()
            assert state["fault_active"] is False
            assert state["delay_seconds"] == 0
            assert state["active_requests"] == 0

    asyncio.run(scenario())


@pytest.mark.parametrize("kind,expected_code", [
    ("connect", "DOWNSTREAM_UNAVAILABLE"), ("pool", "DOWNSTREAM_UNAVAILABLE"),
    ("status", "DOWNSTREAM_HTTP_ERROR"),
])
def test_other_http_errors_are_not_mislabeled_read_timeouts(kind, expected_code, caplog) -> None:
    # Only non-core error discrimination is simulated; timeout/recovery uses real TCP tests.
    def respond(request: httpx.Request) -> httpx.Response:
        if kind == "connect":
            raise httpx.ConnectError("controlled test", request=request)
        if kind == "pool":
            raise httpx.PoolTimeout("controlled test", request=request)
        return httpx.Response(500, json={"detail": "downstream error"})

    app = create_app(Settings(_env_file=None, postgres_password="unused", fault_lab_enabled=False))

    async def scenario() -> None:
        async with app.router.lifespan_context(app), httpx.AsyncClient(
            transport=httpx.MockTransport(respond), base_url="http://dependency",
        ) as dependency, httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://app",
        ) as client:
            app.state.http_client = dependency
            response = await client.get("/downstream/value")
            assert response.status_code == 502
            assert response.json()["error"]["code"] == expected_code
            assert (await client.get("/lab/diagnostics/downstream")).status_code == 404

    with caplog.at_level(logging.INFO, logger="fault_lab"):
        asyncio.run(scenario())
    records = [json.loads(record.message.split("evidence=", 1)[1])
               for record in caplog.records if record.message.startswith("evidence=")]
    failure = next(r for r in records if r["error_type"] == expected_code)
    assert failure["scenario_id"] is None
    assert failure["dependency"] == "controlled-http"


def test_evidence_preserves_unknowns_and_rejects_negative_latency() -> None:
    evidence = Evidence(source="application", event_type="http_request")
    assert evidence.incident_id is None
    assert evidence.scenario_id is None
    assert evidence.latency_ms is None
    assert evidence.timestamp.utcoffset().total_seconds() == 0
    with pytest.raises(ValidationError):
        Evidence(source="application", event_type="http_request", latency_ms=-1)
