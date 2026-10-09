"""Small observation contract; scenario labels are not a diagnosis engine."""

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    schema_version: Literal[1] = 1
    source: Literal["application", "reproduction"]
    event_type: Literal["http_request", "scenario_observation"]
    incident_id: str | None = None
    scenario_id: str | None = None
    request_id: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    service: str = "investigator-app"
    dependency: str | None = None
    error_type: str | None = None
    latency_ms: float | None = Field(default=None, ge=0)
    observations: dict[str, Any] = Field(default_factory=dict)
