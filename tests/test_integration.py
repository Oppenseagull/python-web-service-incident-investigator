import asyncio
import os

import httpx
import pytest

from scripts.reproduce_db_pool_exhaustion import reproduce

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="Set RUN_INTEGRATION=1 with Compose running"),
]


def test_real_postgres_pool_exhaustion_and_recovery() -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(
            base_url=os.getenv("LAB_BASE_URL", "http://127.0.0.1:8000"),
            timeout=15, trust_env=False,
        ) as client:
            assert (await client.get("/healthz")).status_code == 200
            normal = await client.get("/items/1")
            assert normal.status_code == 200
            assert normal.json() == {"id": 1, "name": "Notebook"}
            assert (await client.get("/items/999999")).status_code == 404
            for invalid in (0, -1, 61):
                assert (await client.post(
                    "/lab/faults/db-pool/hold", json={"hold_seconds": invalid},
                )).status_code == 422
            await reproduce(client)

    asyncio.run(scenario())
