"""Validated ToolCall -> fixed registry -> safe access -> validated ToolResult."""

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Callable

import httpx
from pydantic import ValidationError

from app.investigator.contracts import (
    CALL_ADAPTER, EmptyArgs, EventQuery, HealthData, HealthObservation, Observation,
    PoolObservation, ToolCall, ToolResult,
)
from app.investigator.evidence import SafeEvidenceStore, project_pool

RETENTION_LIMIT = "process_local_bounded_cache_restart_loses_data"


class ToolRegistry:
    def __init__(self, store: SafeEvidenceStore, pool_snapshot: Callable[[], dict],
                 http_client: httpx.AsyncClient, read_timeout_seconds: float):
        self._store = store
        self._pool_snapshot = pool_snapshot
        self._http_client = http_client
        self._read_timeout = read_timeout_seconds
        self._handlers = {
            "get_recent_app_events": self._events,
            "get_db_pool_snapshot": self._pool,
            "check_downstream_health": self._health,
        }

    async def execute(self, call: dict | ToolCall) -> ToolResult:
        start = time.perf_counter()
        try:
            validated = CALL_ADAPTER.validate_python(call)
        except ValidationError:
            return ToolResult(call_id=uuid.uuid4().hex, tool_name=None, status="error",
                              error_code="INVALID_TOOL_CALL", duration_ms=(time.perf_counter() - start) * 1000)
        try:
            async with asyncio.timeout(2):
                payload = await self._handlers[validated.tool_name](validated.arguments)
            return ToolResult(call_id=validated.call_id, tool_name=validated.tool_name,
                              duration_ms=(time.perf_counter() - start) * 1000, **payload)
        except (TimeoutError, httpx.TimeoutException):
            payload = {"status": "error", "error_code": "TOOL_TIMEOUT"}
        except httpx.RequestError:
            payload = {"status": "unavailable", "error_code": "TARGET_UNREACHABLE"}
        except Exception:
            # Never expose raw exceptions, URLs, SQL, credentials or filesystem paths.
            payload = {"status": "error", "error_code": "TOOL_ERROR"}
        return ToolResult(call_id=validated.call_id, tool_name=validated.tool_name,
                          duration_ms=(time.perf_counter() - start) * 1000, **payload)

    def get_evidence(self, evidence_id: str) -> Observation | None:
        """Lookup a safe observation only; None means absent/expired/evicted."""
        return self._store.get(evidence_id)

    async def _events(self, arguments: EventQuery) -> dict:
        observations, truncated, evicted = self._store.query(arguments)
        limitations = [RETENTION_LIMIT, "request_end_timestamps_not_request_start"]
        if evicted:
            limitations.append("cache_has_evicted_records_history_may_be_incomplete")
        missing = sorted({name for record in observations for name in ("request_id", "latency_ms")
                          if (record.request_id if name == "request_id" else record.data.latency_ms) is None})
        return {"status": "ok" if observations else "unavailable",
                "error_code": None if observations else "NO_MATCHING_EVENTS",
                "observations": observations, "truncated": truncated, "limitations": limitations,
                "missing_fields": missing}

    async def _pool(self, arguments: EmptyArgs) -> dict:
        observation = PoolObservation(observed_at=datetime.now(timezone.utc),
                                      data=project_pool(self._pool_snapshot()))
        self._store.append(observation)
        missing = [name for name in type(observation.data).model_fields
                   if getattr(observation.data, name) is None]
        available = len(missing) < len(type(observation.data).model_fields)
        return {"status": "ok" if available else "unavailable", "observations": [observation],
                "error_code": None if available else "OBSERVATION_UNAVAILABLE",
                "missing_fields": missing,
                "limitations": ["instantaneous_process_pool_not_historical_or_postgres_global", RETENTION_LIMIT]}

    async def _health(self, arguments: EmptyArgs) -> dict:
        start = time.perf_counter()
        # Only this configured path; no caller URL, redirects, state or mutation API.
        async with self._http_client.stream("GET", "/healthz", timeout=httpx.Timeout(1),
                                            follow_redirects=False) as response:
            body = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=1024):
                if len(body) + len(chunk) > 4096:
                    return {"status": "error", "error_code": "INVALID_TARGET_RESPONSE"}
                body.extend(chunk)
            try:
                healthy = json.loads(body) == {"status": "ok"}
            except (ValueError, UnicodeError):
                healthy = False
            observation = HealthObservation(observed_at=datetime.now(timezone.utc), data=HealthData(
                status_code=response.status_code, health_status="ok" if healthy else None,
                latency_ms=(time.perf_counter() - start) * 1000,
                read_timeout_seconds=self._read_timeout,
            ))
        self._store.append(observation)
        successful = healthy and response.status_code == 200
        return {"status": "ok" if successful else "error", "observations": [observation],
                "error_code": None if successful else "INVALID_TARGET_RESPONSE",
                "missing_fields": [] if healthy else ["health_status"],
                "limitations": ["current_healthz_liveness_does_not_prove_value_path_health", RETENTION_LIMIT]}
