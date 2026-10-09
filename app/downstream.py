import logging
import time

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()
lab_router = APIRouter()
logger = logging.getLogger("fault_lab")


@router.get("/downstream/value")
async def downstream_value(request: Request) -> JSONResponse:
    request.state.dependency = "controlled-http"
    request.state.observations = {
        "target_path": "/value",
        "read_timeout_seconds": request.app.state.settings.downstream_read_timeout,
    }
    start = time.perf_counter()
    try:
        response = await request.app.state.http_client.get(
            "/value", headers={"X-Request-ID": request.state.request_id},
        )
        response.raise_for_status()
    except httpx.ReadTimeout:
        request.state.error_type = "DOWNSTREAM_HTTP_TIMEOUT"
        request.state.scenario_id = "downstream-http-timeout"
        request.state.observations["exception_class"] = "ReadTimeout"
        logger.warning("DOWNSTREAM_HTTP_TIMEOUT path=%s request_id=%s dependency=controlled-http",
                       request.url.path, request.state.request_id)
        return JSONResponse(status_code=504, content={"error": {
            "code": "DOWNSTREAM_HTTP_TIMEOUT",
            "message": "Downstream response exceeded read timeout",
        }})
    except httpx.HTTPStatusError as exc:
        request.state.error_type = "DOWNSTREAM_HTTP_ERROR"
        request.state.observations["downstream_status"] = exc.response.status_code
        return JSONResponse(status_code=502, content={"error": {
            "code": "DOWNSTREAM_HTTP_ERROR", "message": "Downstream returned an error",
        }})
    except httpx.RequestError as exc:
        # Connect/network/HTTP-client-pool errors are distinct from ReadTimeout.
        request.state.error_type = "DOWNSTREAM_UNAVAILABLE"
        request.state.observations["exception_class"] = type(exc).__name__
        return JSONResponse(status_code=502, content={"error": {
            "code": "DOWNSTREAM_UNAVAILABLE", "message": "Downstream request failed",
        }})
    finally:
        request.state.observations["dependency_latency_ms"] = round(
            (time.perf_counter() - start) * 1000, 2,
        )
    return JSONResponse(content=response.json())


@lab_router.get("/lab/diagnostics/downstream")
async def downstream_diagnostics(request: Request) -> dict[str, str | float]:
    # Local configuration only; does not query or alter the dependency.
    return {"dependency": "controlled-http", "target_path": "/value",
            "read_timeout_seconds": request.app.state.settings.downstream_read_timeout}
