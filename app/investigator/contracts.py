"""Closed input/output schemas for the S1 read-only tools."""

import uuid
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, TypeAdapter, model_validator


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")


RequestID = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{32}$")]
Duration = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]
Count = Annotated[int, Field(strict=True, ge=0)]
ErrorType = Literal["DB_POOL_TIMEOUT", "DOWNSTREAM_HTTP_TIMEOUT", "DOWNSTREAM_UNAVAILABLE",
                    "DOWNSTREAM_HTTP_ERROR", "UNHANDLED_ERROR"]
ExceptionClass = Literal[
    "sqlalchemy.exc.TimeoutError", "ReadTimeout", "ConnectTimeout", "WriteTimeout",
    "PoolTimeout", "ConnectError", "ReadError", "WriteError", "CloseError",
    "LocalProtocolError", "RemoteProtocolError", "ProxyError", "UnsupportedProtocol",
    "TooManyRedirects", "DecodingError",
]


class EventQuery(ClosedModel):
    request_id: RequestID | None = None
    start_time: AwareDatetime | None = None
    end_time: AwareDatetime | None = None
    limit: Annotated[int, Field(strict=True, ge=1, le=50)] = 20

    @model_validator(mode="after")
    def bounded_query(self) -> "EventQuery":
        if (self.start_time is None) != (self.end_time is None):
            raise ValueError("Provide both window bounds")
        if self.start_time is None:
            if self.request_id is None:
                raise ValueError("Provide request_id or a time window")
        elif not 0 <= (self.end_time - self.start_time).total_seconds() <= 300:
            raise ValueError("Window must be ordered and at most 300 seconds")
        return self


class EmptyArgs(ClosedModel):
    pass


class RecentEventsCall(ClosedModel):
    call_id: RequestID = Field(default_factory=lambda: uuid.uuid4().hex)
    tool_name: Literal["get_recent_app_events"]
    arguments: EventQuery


class PoolCall(ClosedModel):
    call_id: RequestID = Field(default_factory=lambda: uuid.uuid4().hex)
    tool_name: Literal["get_db_pool_snapshot"]
    arguments: EmptyArgs = Field(default_factory=EmptyArgs)


class HealthCall(ClosedModel):
    call_id: RequestID = Field(default_factory=lambda: uuid.uuid4().hex)
    tool_name: Literal["check_downstream_health"]
    arguments: EmptyArgs = Field(default_factory=EmptyArgs)


ToolCall = Annotated[RecentEventsCall | PoolCall | HealthCall, Field(discriminator="tool_name")]
CALL_ADAPTER = TypeAdapter(ToolCall)


class PoolData(ClosedModel):
    configured_pool_size: Count | None = None
    configured_max_overflow: Count | None = None
    pool_timeout_seconds: Duration | None = None
    checked_out: Count | None = None
    checked_in: Count | None = None
    # SQLAlchemy's lazy pool can report negative overflow.
    overflow: Annotated[int, Field(strict=True)] | None = None


class AppEventData(ClosedModel):
    path: Annotated[str, Field(strict=True, pattern=r"^(?:/healthz|/downstream/value|/items/-?[0-9]{1,20})$")]
    status_code: Annotated[int, Field(strict=True, ge=100, le=599)]
    dependency: Literal["postgres", "controlled-http"] | None = None
    error_type: ErrorType | None = None
    latency_ms: Duration | None = None
    exception_class: ExceptionClass | None = None
    db_pool: PoolData | None = None
    target_path: Literal["/value"] | None = None
    read_timeout_seconds: Duration | None = None
    dependency_latency_ms: Duration | None = None
    downstream_status: Annotated[int, Field(strict=True, ge=100, le=599)] | None = None


class HealthData(ClosedModel):
    dependency: Literal["controlled-http"] = "controlled-http"
    target_path: Literal["/healthz"] = "/healthz"
    status_code: Annotated[int, Field(strict=True, ge=100, le=599)] | None = None
    health_status: Literal["ok"] | None = None
    latency_ms: Duration
    read_timeout_seconds: Duration


class ObservationBase(ClosedModel):
    evidence_id: RequestID = Field(default_factory=lambda: uuid.uuid4().hex)
    observed_at: AwareDatetime
    service: Literal["investigator-app"] = "investigator-app"


class AppObservation(ObservationBase):
    source: Literal["app_request"] = "app_request"
    request_id: RequestID | None = None
    data: AppEventData


class PoolObservation(ObservationBase):
    source: Literal["db_pool"] = "db_pool"
    data: PoolData


class HealthObservation(ObservationBase):
    source: Literal["downstream_health"] = "downstream_health"
    data: HealthData


Observation = Annotated[AppObservation | PoolObservation | HealthObservation, Field(discriminator="source")]
ToolName = Literal["get_recent_app_events", "get_db_pool_snapshot", "check_downstream_health"]
FailureCode = Literal["INVALID_TOOL_CALL", "NO_MATCHING_EVENTS", "EVIDENCE_NOT_RETAINED",
                      "TARGET_UNREACHABLE", "TOOL_TIMEOUT", "TOOL_ERROR", "INVALID_TARGET_RESPONSE",
                      "OBSERVATION_UNAVAILABLE"]


class ToolResult(ClosedModel):
    call_id: RequestID
    tool_name: ToolName | None
    status: Literal["ok", "error", "unavailable"]
    observations: Annotated[list[Observation], Field(max_length=50)] = Field(default_factory=list)
    duration_ms: Duration
    truncated: bool = False
    error_code: FailureCode | None = None
    missing_fields: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_status(self) -> "ToolResult":
        if (self.status == "ok") != (self.error_code is None):
            raise ValueError("Non-ok results require an error code")
        if self.status == "ok" and not self.observations:
            raise ValueError("Ok results require actual observations")
        expected = {"get_recent_app_events": "app_request", "get_db_pool_snapshot": "db_pool",
                    "check_downstream_health": "downstream_health"}.get(self.tool_name)
        if any(observation.source != expected for observation in self.observations):
            raise ValueError("Observation source must match the requested tool")
        return self
