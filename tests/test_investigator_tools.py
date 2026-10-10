"""Contract, provenance, leakage, retention and execution-boundary checks."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.evidence import Evidence
from app.investigator.contracts import EventQuery, PoolCall, ToolResult
from app.investigator.evidence import SafeEvidenceStore, project_event
from app.investigator.tools import ToolRegistry

REQUEST_ID = "a" * 32
NOW = datetime.now(timezone.utc)
POOL = {"configured_pool_size": 2, "configured_max_overflow": 0, "pool_timeout_seconds": 1.0,
        "checked_out": 2, "checked_in": 0, "overflow": 0}


def raw_event(**changes):
    values = {"source": "application", "event_type": "http_request", "timestamp": NOW,
              "request_id": REQUEST_ID, "scenario_id": "db-pool-exhaustion",
              "incident_id": "controller-run-SECRET", "dependency": "postgres",
              "error_type": "DB_POOL_TIMEOUT", "latency_ms": 1001.0,
              "observations": {"path": "/items/1", "status_code": 503,
                               "exception_class": "sqlalchemy.exc.TimeoutError", "db_pool": POOL}}
    values.update(changes)
    return Evidence(**values)


async def with_registry(run, store=None, snapshot=lambda: POOL, handler=None):
    store = store or SafeEvidenceStore()
    async with httpx.AsyncClient(base_url="http://dependency", trust_env=False,
                                 transport=httpx.MockTransport(handler or (
                                     lambda request: httpx.Response(200, json={"status": "ok"})
                                 ))) as client:
        return await run(ToolRegistry(store, snapshot, client, 1.0))


def test_projection_query_and_references_exclude_ground_truth_at_every_level():
    secret = "downstream-http-timeout"
    store = SafeEvidenceStore()
    fields = {**raw_event().observations, "fault_active": True, "delay_seconds": 3,
              "ttl": 10, "expected_root_cause": secret, "path_to_answer": "C:/secret",
              "nested": {"scenario_id": secret},
              "db_pool": {**POOL, "scenario_id": secret, "nested": {"fault_active": True}}}
    store.capture(raw_event(observations=fields))
    store.capture(raw_event(source="reproduction", event_type="scenario_observation"))

    async def run(registry):
        call = {"tool_name": "get_recent_app_events", "arguments": {"request_id": REQUEST_ID}}
        first = await registry.execute(call)
        second = await registry.execute(call)
        assert first.status == "ok" and len(first.observations) == 1
        record = first.observations[0]
        assert record.request_id == REQUEST_ID
        assert record.data.db_pool.checked_out == 2
        assert record.data.error_type == "DB_POOL_TIMEOUT"
        assert record.evidence_id == second.observations[0].evidence_id
        assert registry.get_evidence(record.evidence_id) == record
        assert registry.get_evidence("f" * 32) is None
        encoded = first.model_dump_json()
        for banned in ("scenario_id", "incident_id", "controller-run-SECRET", "db-pool-exhaustion",
                       secret, "fault_active", "delay_seconds", "ttl", "expected_root_cause",
                       "C:/secret", "nested"):
            assert banned not in encoded
        ToolResult.model_validate_json(encoded)

    asyncio.run(with_registry(run, store=store))


@pytest.mark.parametrize("path", ["/lab/faults/db-pool/hold", "/lab/faults/response-delay",
                                  "/lab/diagnostics/state", "/lab/diagnostics/db-pool",
                                  "/items/scenario_id=secret", "/docs", "/unknown"])
def test_control_and_unapproved_routes_never_enter_cache(path):
    store = SafeEvidenceStore()
    store.capture(raw_event(observations={"path": path, "status_code": 200}))
    assert store.query(EventQuery(request_id=REQUEST_ID))[0] == []


@pytest.mark.parametrize("call", [
    {"tool_name": "shell", "arguments": {"command": "cat answer"}},
    {"tool_name": "get_db_pool_snapshot", "arguments": {"sql": "SELECT 1"}},
    {"tool_name": "check_downstream_health", "arguments": {"url": "http://other"}},
    {"tool_name": "get_recent_app_events", "arguments": {}},
    {"tool_name": "get_recent_app_events", "arguments": {"request_id": REQUEST_ID, "limit": 51}},
    {"tool_name": "get_recent_app_events", "arguments": {"request_id": REQUEST_ID, "limit": 0}},
    {"tool_name": "get_recent_app_events", "arguments": {"request_id": REQUEST_ID, "limit": "2"}},
    {"tool_name": "get_recent_app_events", "arguments": {"request_id": REQUEST_ID, "limit": True}},
    {"tool_name": "get_recent_app_events", "arguments": {"request_id": "secret"}},
    {"tool_name": "get_recent_app_events", "arguments": {"start_time": NOW.isoformat(),
      "end_time": (NOW + timedelta(seconds=301)).isoformat()}},
    {"tool_name": "get_recent_app_events", "arguments": {"start_time": NOW.isoformat()}},
    {"tool_name": "get_recent_app_events", "arguments": {"start_time": NOW.isoformat(),
      "end_time": (NOW - timedelta(seconds=1)).isoformat()}},
    {"tool_name": "get_recent_app_events", "arguments": {"start_time": "2026-10-10T00:00:00",
      "end_time": "2026-10-10T00:01:00"}},
    {"tool_name": "get_db_pool_snapshot", "arguments": {}, "scenario_id": "answer"},
])
def test_invalid_calls_rejected_before_any_execution(call):
    def forbidden(*args):
        pytest.fail("Invalid call performed IO")

    async def run(registry):
        result = await registry.execute(call)
        assert result.status == "error" and result.error_code == "INVALID_TOOL_CALL"
        assert result.observations == []
        assert "answer" not in result.model_dump_json()

    asyncio.run(with_registry(run, snapshot=forbidden, handler=forbidden))


def test_incomplete_data_is_null_not_zero_and_results_are_copies():
    store = SafeEvidenceStore()
    store.capture(raw_event(latency_ms=None))

    async def run(registry):
        event = (await registry.execute({"tool_name": "get_recent_app_events",
                                         "arguments": {"request_id": REQUEST_ID}})).observations[0]
        assert event.data.latency_ms is None
        pool = await registry.execute(PoolCall(tool_name="get_db_pool_snapshot"))
        assert pool.observations[0].data.checked_out is None
        assert "checked_out" in pool.missing_fields
        assert pool.observations[0].data.overflow == -2
        assert pool.observations[0].evidence_id != event.evidence_id
        assert registry.get_evidence(pool.observations[0].evidence_id) == pool.observations[0]

    asyncio.run(with_registry(run, store=store, snapshot=lambda: {"overflow": -2}))


def test_constructed_model_cannot_bypass_argument_validation_and_no_data_is_unavailable():
    async def run(registry):
        bypass = PoolCall.model_construct(tool_name="get_db_pool_snapshot", arguments={"sql": "answer"})
        assert (await registry.execute(bypass)).error_code == "INVALID_TOOL_CALL"
        empty = await registry.execute({"tool_name": "get_db_pool_snapshot"})
        assert empty.status == "unavailable" and empty.error_code == "OBSERVATION_UNAVAILABLE"
        assert len(empty.missing_fields) == 6
    asyncio.run(with_registry(run, snapshot=lambda: {}))


def test_time_window_limit_eviction_and_restart():
    clock = [0.0]
    store = SafeEvidenceStore(capacity=2, ttl_seconds=10, clock=lambda: clock[0])
    ids = []
    for n in range(3):
        event = project_event(raw_event(timestamp=NOW + timedelta(seconds=n)))
        ids.append(event.evidence_id)
        store.append(event)
    query = EventQuery(start_time=NOW, end_time=NOW + timedelta(seconds=3), limit=1)
    results, truncated, evicted = store.query(query)
    assert results[0].evidence_id == ids[2] and truncated and evicted
    assert store.get(ids[0]) is None
    clock[0] = 11
    assert store.get(ids[2]) is None
    assert store.query(query)[0] == []
    assert SafeEvidenceStore().query(query)[0] == []


def test_cache_concurrent_writes_remain_bounded():
    store = SafeEvidenceStore(capacity=10)
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda _: store.capture(raw_event()), range(100)))
    records, truncated, evicted = store.query(EventQuery(request_id=REQUEST_ID, limit=50))
    assert len(records) == 10 and evicted and not truncated
    assert len({record.evidence_id for record in records}) == 10


def test_structured_no_results_and_internal_failure_do_not_echo_secrets():
    def broken():
        raise RuntimeError("postgres://secret-password@host C:/answer")

    async def run(registry):
        missing = await registry.execute({"tool_name": "get_recent_app_events",
                                          "arguments": {"request_id": REQUEST_ID}})
        assert missing.status == "unavailable" and missing.error_code == "NO_MATCHING_EVENTS"
        failed = await registry.execute({"tool_name": "get_db_pool_snapshot"})
        assert failed.status == "error" and failed.error_code == "TOOL_ERROR"
        assert "secret-password" not in failed.model_dump_json()

    asyncio.run(with_registry(run, snapshot=broken))


@pytest.mark.parametrize("mode,expected", [("connect", "TARGET_UNREACHABLE"),
                                           ("timeout", "TOOL_TIMEOUT"),
                                           ("redirect", "INVALID_TARGET_RESPONSE"),
                                           ("large", "INVALID_TARGET_RESPONSE"),
                                           ("malformed", "INVALID_TARGET_RESPONSE")])
def test_health_errors_are_bounded_and_never_follow_redirects(mode, expected):
    calls = []

    def handler(request):
        calls.append(request)
        assert request.method == "GET" and request.url.path == "/healthz"
        assert request.url.host == "dependency"
        if mode == "connect":
            raise httpx.ConnectError("secret-host", request=request)
        if mode == "timeout":
            raise httpx.ReadTimeout("secret-host", request=request)
        if mode == "redirect":
            return httpx.Response(302, headers={"Location": "http://other/lab/faults/response-delay"})
        if mode == "large":
            return httpx.Response(200, content=b"x" * 4097)
        return httpx.Response(200, json={"status": {"scenario_id": "answer"}})

    async def run(registry):
        result = await registry.execute({"tool_name": "check_downstream_health"})
        assert result.error_code == expected
        assert result.status in ("error", "unavailable")
        assert "secret-host" not in result.model_dump_json()
        assert "scenario_id" not in result.model_dump_json()

    asyncio.run(with_registry(run, handler=handler))
    assert len(calls) == 1


def test_fixed_health_probe_returns_only_approved_fields():
    async def run(registry):
        result = await registry.execute({"tool_name": "check_downstream_health"})
        assert result.status == "ok"
        assert result.observations[0].data.health_status == "ok"
        assert registry.get_evidence(result.observations[0].evidence_id) == result.observations[0]
    asyncio.run(with_registry(run))


def test_backend_hard_timeout_and_invalid_output_are_structured():
    async def run(registry):
        async def hung(args):
            await asyncio.sleep(5)
        registry._handlers["get_db_pool_snapshot"] = hung
        failed = await registry.execute({"tool_name": "get_db_pool_snapshot"})
        assert failed.error_code == "TOOL_TIMEOUT" and failed.duration_ms < 3000

        async def malformed(args):
            return {"status": "ok", "observations": [], "secret": "answer"}
        registry._handlers["get_db_pool_snapshot"] = malformed
        invalid = await registry.execute({"tool_name": "get_db_pool_snapshot"})
        assert invalid.error_code == "TOOL_ERROR"
        assert "answer" not in invalid.model_dump_json()
    asyncio.run(with_registry(run))
