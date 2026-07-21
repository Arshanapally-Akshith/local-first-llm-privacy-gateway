"""FastAPI entrypoint for the privacy gateway.

Constructs Settings and configures logging at import time, before the
FastAPI app object exists — so `uvicorn app.main:app` fails on a
misconfigured environment at startup, never at first request (BUILD.md
Phase 0 DoD: "missing required var fails loudly at startup, not at
first request"). The Tier-2 model warmup below extends this same
posture to a second kind of startup failure (Phase 4): a model that
can't load fails the same way a bad Settings value already does — loud,
at boot, before the server binds — never silently on the first request
that happens to need it.
"""

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.core.config import get_settings
from src.core.exceptions import SurrogateDomainError, UpstreamError
from src.core.fail_mode import FailClosedError
from src.core.logging import configure_logging, get_gateway_logger, log_event
from src.detect.tier2.gliner_model import get_tier2_model
from src.proxy.routes import router as proxy_router

settings = get_settings()
configure_logging(settings.log_level)


def _warm_tier2_model() -> None:
    """Load the Tier-2 model and run one real inference through it,
    before the server starts accepting requests.

    BUILD.md, Phase 4: "Cold start is real. First inference is
    seconds. Warm the model at startup and say so — do not let it hide
    inside p50 later." The warmup call itself isn't wired through
    `Tier2Detector`/`cascade.py` yet (that's Phase 4 Task 3) — calling
    `Tier2Model.find_entities()` directly is sufficient to force both
    the model load *and* the first-inference cost this stage exists to
    absorb, and needs no cascade wiring to do it.
    """
    start = time.perf_counter()
    model = get_tier2_model()
    model.find_entities("Warm-up call.")
    elapsed_ms = (time.perf_counter() - start) * 1000
    log_event(
        get_gateway_logger(),
        "startup.tier2_model_warmed",
        correlation_id="startup",
        latency_ms=elapsed_ms,
    )


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Warms the Tier-2 model before the server starts accepting
    requests, if `NER_WARMUP` is enabled (default `True` — see
    `src/core/config.py`)."""
    if settings.ner_warmup:
        _warm_tier2_model()
    yield


app = FastAPI(lifespan=_lifespan)
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


@app.exception_handler(SurrogateDomainError)
async def _handle_surrogate_domain_error(
    _request: Request, exc: SurrogateDomainError
) -> JSONResponse:
    """Turn a raised SurrogateDomainError into a 500.

    ARCHITECTURE.md's Error Handling flowchart treats a surrogate
    domain mismatch as its own fixed branch — always a 500, never a
    pass-through, half-sanitised = leak. FastAPI's default handler for
    an unregistered exception type would already produce a 500, but
    not with this project's consistent JSON error shape; mirrors the
    UpstreamError handler above. `str(exc)` is safe to return: every
    SurrogateDomainError message states what failed and the expected
    shape, never the real value (see the exception's own docstring).
    """
    return JSONResponse(status_code=500, content={"error": str(exc)})


@app.exception_handler(FailClosedError)
async def _handle_fail_closed_error(_request: Request, exc: FailClosedError) -> JSONResponse:
    """Turn a raised FailClosedError into a 503.

    `src/core/fail_mode.py`'s own docstring names this mapping in
    advance: "The proxy layer, not this module, maps this to a 503" —
    `core` must not depend on the proxy layer or know about HTTP. This
    is FAIL_MODE=closed's real, observable behaviour (ARCHITECTURE.md,
    Error Handling: "closed -> 503, caller is down") for a Tier-2
    detection failure (Phase 4 Task 4) — the first stage this
    dispatch mechanism actually guards for real.
    """
    return JSONResponse(status_code=503, content={"error": str(exc)})


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe.

    No auth, no upstream call, no request body — this endpoint must stay
    trivially cheap and cannot itself become a PII surface.
    """
    return {"status": "ok"}
