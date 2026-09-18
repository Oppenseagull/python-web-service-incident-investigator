import asyncio
import logging

import httpx

from app.config import Settings
from app.main import create_app


def test_health_and_lab_disabled_without_database(caplog) -> None:
    settings = Settings(_env_file=None, postgres_password="test-only", fault_lab_enabled=False)
    app = create_app(settings)
    async def scenario() -> None:
        async with app.router.lifespan_context(app), httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            response = await client.get("/healthz")
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}
            assert len(response.headers["x-request-id"]) == 32
            assert "request_id=" + response.headers["x-request-id"] in caplog.text
            assert "path=/healthz status=200" in caplog.text
            assert "latency_ms=" in caplog.text
            assert (await client.get("/lab/diagnostics/db-pool")).status_code == 404
            assert (await client.post("/lab/faults/db-pool/hold", json={"hold_seconds": 5})).status_code == 404
            schema = (await client.get("/openapi.json")).json()
            assert not any(path.startswith("/lab/") for path in schema["paths"])

    with caplog.at_level(logging.INFO, logger="fault_lab"):
        asyncio.run(scenario())


def test_unexpected_errors_are_not_pool_timeouts() -> None:
    app = create_app(Settings(_env_file=None, postgres_password="test-only", fault_lab_enabled=False))

    @app.get("/test-programming-error")
    async def broken() -> None:
        raise ValueError("deliberate programming error")

    async def scenario() -> None:
        async with app.router.lifespan_context(app), httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            response = await client.get("/test-programming-error")
            assert response.status_code == 500
            assert "DB_POOL_TIMEOUT" not in response.text
            assert "deliberate programming error" not in response.text

    asyncio.run(scenario())
