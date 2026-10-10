import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import AsyncAdaptedQueuePool
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.config import Settings
from app.database import create_engine, get_session
from app.downstream import lab_router, router
from app.evidence import Evidence
from app.investigator.evidence import SafeEvidenceStore
from app.investigator.tools import ToolRegistry

logger = logging.getLogger("fault_lab")
Session = Annotated[AsyncSession, Depends(get_session)]


class HoldRequest(BaseModel):
    hold_seconds: float = Field(default=5, gt=0, le=60, allow_inf_nan=False)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = create_engine(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            async with httpx.AsyncClient(
                base_url=str(settings.downstream_base_url), trust_env=False,
                timeout=httpx.Timeout(2, read=settings.downstream_read_timeout),
            ) as client:
                app.state.http_client = client
                app.state.investigator_tools = ToolRegistry(
                    app.state.safe_evidence, pool_snapshot, client, settings.downstream_read_timeout,
                )
                yield
        finally:
            await engine.dispose()

    app = FastAPI(title="Incident Fault Lab", lifespan=lifespan)
    app.state.settings = settings
    app.state.sessions = async_sessionmaker(engine, expire_on_commit=False)
    app.state.safe_evidence = SafeEvidenceStore()
    app.include_router(router)

    def pool_snapshot() -> dict[str, int | float]:
        pool = engine.pool
        assert isinstance(pool, AsyncAdaptedQueuePool)
        return {
            "configured_pool_size": pool.size(),
            "configured_max_overflow": settings.db_max_overflow,
            "pool_timeout_seconds": pool.timeout(),
            "checked_out": pool.checkedout(), "checked_in": pool.checkedin(),
            "overflow": pool.overflow(),
        }

    @app.middleware("http")
    async def log_request(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.request_id = uuid.uuid4().hex
        request.state.dependency = None
        request.state.scenario_id = None
        request.state.error_type = None
        request.state.observations = {}
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request.state.request_id
            return response
        finally:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.info(
                "request path=%s status=%s request_id=%s latency_ms=%.2f",
                request.url.path, status, request.state.request_id,
                latency_ms,
            )
            evidence = Evidence(
                source="application", event_type="http_request",
                request_id=request.state.request_id,
                scenario_id=request.state.scenario_id,
                dependency=request.state.dependency,
                error_type=request.state.error_type or ("UNHANDLED_ERROR" if status == 500 else None),
                latency_ms=latency_ms,
                observations={"path": request.url.path, "status_code": status,
                              **request.state.observations},
            )
            logger.info("evidence=%s", evidence.model_dump_json())
            app.state.safe_evidence.capture(evidence)

    @app.exception_handler(SQLAlchemyTimeoutError)
    async def pool_timeout(request: Request, exc: SQLAlchemyTimeoutError) -> JSONResponse:
        request.state.dependency = "postgres"
        request.state.scenario_id = "db-pool-exhaustion"
        request.state.error_type = "DB_POOL_TIMEOUT"
        request.state.observations = {"exception_class": "sqlalchemy.exc.TimeoutError",
                                      "db_pool": pool_snapshot()}
        # Catch only SQLAlchemy's timeout, not arbitrary application exceptions.
        logger.warning(
            "DB_POOL_TIMEOUT path=%s request_id=%s",
            request.url.path, request.state.request_id,
        )
        return JSONResponse(status_code=503, content={"error": {
            "code": "DB_POOL_TIMEOUT",
            "message": "Database connection pool temporarily exhausted",
        }})

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/items/{item_id}")
    async def get_item(item_id: int, request: Request, session: Session) -> dict[str, int | str]:
        request.state.dependency = "postgres"
        result = await session.execute(
            text("SELECT id, name FROM items WHERE id = :item_id"),
            {"item_id": item_id},
        )
        row = result.mappings().one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Item not found")
        return {"id": row["id"], "name": row["name"]}

    if settings.fault_lab_enabled:
        app.include_router(lab_router)
        @app.post("/lab/faults/db-pool/hold")
        async def hold_connection(body: HoldRequest, request: Request, session: Session) -> dict[str, float]:
            request.state.dependency = "postgres"
            await session.execute(text("SELECT 1"))
            # No commit/rollback here: the transaction retains its real connection.
            await asyncio.sleep(body.hold_seconds)
            return {"held_seconds": body.hold_seconds}

        @app.get("/lab/diagnostics/db-pool")
        async def pool_diagnostics() -> dict[str, int | float]:
            # Public pool methods; this route never acquires a DB connection.
            return pool_snapshot()

    return app
