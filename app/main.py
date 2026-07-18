"""FastAPI entrypoint for the privacy gateway.

Constructs Settings and configures logging at import time, before the
FastAPI app object exists — so `uvicorn app.main:app` fails on a
misconfigured environment at startup, never at first request (BUILD.md
Phase 0 DoD: "missing required var fails loudly at startup, not at
first request").
"""

from fastapi import FastAPI

from src.core.config import get_settings
from src.core.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI()


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe.

    No auth, no upstream call, no request body — this endpoint must stay
    trivially cheap and cannot itself become a PII surface.
    """
    return {"status": "ok"}
