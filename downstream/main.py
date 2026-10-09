"""Controlled HTTP dependency: one read and a bounded, expiring delay fault."""

import asyncio
import logging
import time
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("controlled_http")


class DownstreamSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    fault_lab_enabled: bool = False


class DelayRequest(BaseModel):
    delay_seconds: float = Field(gt=0, le=10, allow_inf_nan=False)
    duration_seconds: float = Field(default=10, gt=0, le=60, allow_inf_nan=False)


def create_app(settings: DownstreamSettings | None = None) -> FastAPI:
    settings = settings or DownstreamSettings()
    app = FastAPI(title="Controlled HTTP dependency")
    # State is intentionally in-memory, local to this single process.
    delay_seconds = 0.0
    expires_at = 0.0
    active_requests = 0
    last_request_id: str | None = None
    last_received_at: str | None = None

    def state() -> dict[str, object]:
        remaining = max(0.0, expires_at - time.monotonic())
        return {"fault_active": remaining > 0,
                "delay_seconds": delay_seconds if remaining > 0 else 0.0,
                "remaining_seconds": round(remaining, 3),
                "active_requests": active_requests,
                "last_request_id": last_request_id, "last_received_at": last_received_at}

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/value")
    async def value(request: Request) -> dict[str, str]:
        nonlocal active_requests, last_request_id, last_received_at
        # Snapshot delay at arrival; reset affects future requests, not this one.
        applied_delay = delay_seconds if time.monotonic() < expires_at else 0.0
        last_request_id = request.headers.get("X-Request-ID")
        last_received_at = datetime.now(timezone.utc).isoformat()
        request_id = last_request_id
        active_requests += 1
        start = time.perf_counter()
        logger.info("dependency_received request_id=%s applied_delay_seconds=%s",
                    request_id, applied_delay)
        try:
            await asyncio.sleep(applied_delay)
            return {"value": "ready"}
        finally:
            active_requests -= 1
            logger.info("dependency_finished request_id=%s latency_ms=%.2f",
                        request_id, (time.perf_counter() - start) * 1000)

    if settings.fault_lab_enabled:
        @app.post("/lab/faults/response-delay")
        async def inject(body: DelayRequest) -> dict[str, object]:
            nonlocal delay_seconds, expires_at
            delay_seconds = body.delay_seconds
            expires_at = time.monotonic() + body.duration_seconds
            return state()

        @app.delete("/lab/faults/response-delay")
        async def reset() -> dict[str, object]:
            nonlocal delay_seconds, expires_at
            delay_seconds = expires_at = 0.0
            return state()

        @app.get("/lab/diagnostics/state")
        async def diagnostics() -> dict[str, object]:
            return state()

    return app
