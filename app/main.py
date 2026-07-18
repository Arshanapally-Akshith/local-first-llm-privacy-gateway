"""FastAPI entrypoint for the privacy gateway.

Constructs Settings and configures logging at import time, before the
FastAPI app object exists — so `uvicorn app.main:app` fails on a
misconfigured environment at startup, never at first request (BUILD.md
Phase 0 DoD: "missing required var fails loudly at startup, not at
first request").
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.core.config import get_settings
from src.core.exceptions import UpstreamError
from src.core.logging import configure_logging
from src.proxy.routes import router as proxy_router

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI()
app.include_router(proxy_router)


@app.exception_handler(UpstreamError)
async def _handle_upstream_error(_request: Request, exc: UpstreamError) -> JSONResponse:
    """Turn a raised UpstreamError into its carried status code.

    FastAPI does not do this for an arbitrary exception type by
    default — without this handler, UpstreamError would surface as a
    generic 500, discarding the 502/504 distinction the proxy layer
    already worked out (ARCHITECTURE.md, Error Handling).
    """
    return JSONResponse(status_code=exc.status_code, content={"error": str(exc)})


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe.

    No auth, no upstream call, no request body — this endpoint must stay
    trivially cheap and cannot itself become a PII surface.
    """
    return {"status": "ok"}
