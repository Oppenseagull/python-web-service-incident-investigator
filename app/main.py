import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

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
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title="M0: DB Pool Fault Lab", lifespan=lifespan)
    app.state.sessions = async_sessionmaker(engine, expire_on_commit=False)

    @app.middleware("http")
    async def log_request(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.request_id = uuid.uuid4().hex
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request.state.request_id
            return response
        finally:
            logger.info(
                "request path=%s status=%s request_id=%s latency_ms=%.2f",
                request.url.path, status, request.state.request_id,
                (time.perf_counter() - start) * 1000,
            )

    @app.exception_handler(SQLAlchemyTimeoutError)
    async def pool_timeout(request: Request, exc: SQLAlchemyTimeoutError) -> JSONResponse:
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
    async def get_item(item_id: int, session: Session) -> dict[str, int | str]:
        result = await session.execute(
            text("SELECT id, name FROM items WHERE id = :item_id"),
            {"item_id": item_id},
        )
        row = result.mappings().one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Item not found")
        return {"id": row["id"], "name": row["name"]}

    if settings.fault_lab_enabled:
        @app.post("/lab/faults/db-pool/hold")
        async def hold_connection(body: HoldRequest, session: Session) -> dict[str, float]:
            await session.execute(text("SELECT 1"))
            # No commit/rollback here: the transaction retains its real connection.
            await asyncio.sleep(body.hold_seconds)
            return {"held_seconds": body.hold_seconds}

        @app.get("/lab/diagnostics/db-pool")
        async def pool_diagnostics() -> dict[str, int | float]:
            pool = engine.pool
            assert isinstance(pool, AsyncAdaptedQueuePool)
            # Public pool methods; this route never acquires a DB connection.
            return {
                "configured_pool_size": pool.size(),
                "configured_max_overflow": settings.db_max_overflow,
                "pool_timeout_seconds": pool.timeout(),
                "checked_out": pool.checkedout(),
                "checked_in": pool.checkedin(),
                "overflow": pool.overflow(),
            }

    return app
