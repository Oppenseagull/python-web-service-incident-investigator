"""Explicit allowlist projection and a process-local bounded safe store."""

import time
from collections import OrderedDict
from threading import Lock
from typing import Callable

from pydantic import ValidationError

from app.evidence import Evidence
from app.investigator.contracts import AppEventData, AppObservation, EventQuery, Observation, PoolData


def project_pool(raw: dict) -> PoolData:
    # Rebuild every level: never serialize or recursively forward the raw dict.
    return PoolData(**{name: raw[name] for name in PoolData.model_fields if name in raw})


def project_event(raw: Evidence) -> AppObservation | None:
    if raw.source != "application" or raw.event_type != "http_request":
        return None
    fields = raw.observations
    try:
        data = AppEventData(
            path=fields.get("path"), status_code=fields.get("status_code"),
            dependency=raw.dependency, error_type=raw.error_type, latency_ms=raw.latency_ms,
            exception_class=fields.get("exception_class"),
            db_pool=project_pool(fields["db_pool"]) if isinstance(fields.get("db_pool"), dict) else None,
            **{name: fields[name] for name in (
                "target_path", "read_timeout_seconds", "dependency_latency_ms", "downstream_status",
            ) if name in fields},
        )
        return AppObservation(observed_at=raw.timestamp, request_id=raw.request_id, data=data)
    except ValidationError:
        # Unknown routes/types/text are excluded rather than echoed into tool errors.
        return None


class SafeEvidenceStore:
    """FIFO + monotonic TTL; locks cover only bounded in-memory operations."""

    def __init__(self, capacity: int = 2000, ttl_seconds: float = 600,
                 clock: Callable[[], float] = time.monotonic):
        if capacity <= 0 or ttl_seconds <= 0:
            raise ValueError("Positive capacity and TTL required")
        self.capacity = capacity
        self.ttl_seconds = ttl_seconds
        self._clock = clock
        self._lock = Lock()
        self._records: OrderedDict[str, tuple[float, Observation]] = OrderedDict()
        self._evicted = False

    def _prune(self, now: float) -> None:
        while self._records:
            _, (added, _) = next(iter(self._records.items()))
            if now - added < self.ttl_seconds:
                break
            self._records.popitem(last=False)
            self._evicted = True

    def append(self, observation: Observation) -> None:
        with self._lock:
            now = self._clock()
            self._prune(now)
            self._records[observation.evidence_id] = (now, observation.model_copy(deep=True))
            self._records.move_to_end(observation.evidence_id)
            while len(self._records) > self.capacity:
                self._records.popitem(last=False)
                self._evicted = True

    def capture(self, evidence: Evidence) -> None:
        projected = project_event(evidence)
        if projected is not None:
            self.append(projected)

    def get(self, evidence_id: str) -> Observation | None:
        with self._lock:
            self._prune(self._clock())
            entry = self._records.get(evidence_id)
            return entry[1].model_copy(deep=True) if entry else None

    def query(self, query: EventQuery) -> tuple[list[AppObservation], bool, bool]:
        with self._lock:
            self._prune(self._clock())
            matches = [record for _, record in self._records.values()
                       if isinstance(record, AppObservation)
                       and (query.request_id is None or record.request_id == query.request_id)
                       and (query.start_time is None or query.start_time <= record.observed_at <= query.end_time)]
            # Timestamp ordering is distinct from monotonic retention ordering.
            matches.sort(key=lambda record: record.observed_at, reverse=True)
            return ([record.model_copy(deep=True) for record in matches[:query.limit]],
                    len(matches) > query.limit, self._evicted)
