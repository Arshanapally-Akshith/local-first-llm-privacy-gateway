"""Injected HTTP client for the configured upstream (mock or live).

A thin factory around `httpx.AsyncClient`, not a wrapper class —
httpx's own client already has the right shape (`.post`, `.stream`) and
is already straightforward to substitute in tests via a custom
transport, so wrapping it in a bespoke class would be ceremony with no
real benefit (CLAUDE.md: "Don't apply SOLID ceremonially. A factory for
a thing with one implementation is bloat.").

What this module owns is the *injection seam*: constructing the client
from Settings once, so routes never construct their own client
per-request or reach for one globally (CLAUDE.md: "the upstream
client... injected, never reached for globally").
"""

from functools import lru_cache

import httpx

from src.core.config import Settings, get_settings


def build_upstream_client(settings: Settings) -> httpx.AsyncClient:
    """Construct the upstream HTTP client from settings.

    `base_url` is `settings.upstream_base_url` regardless of whether
    `UPSTREAM_MODE` is "mock" or "live" — the mock/live distinction is
    purely which URL is configured, never a branch in this code
    (ARCHITECTURE.md: "mock and live upstreams are interchangeable
    purely by which URL is configured").
    """
    return httpx.AsyncClient(base_url=settings.upstream_base_url, timeout=settings.upstream_timeout)


@lru_cache
def get_upstream_client() -> httpx.AsyncClient:
    """FastAPI dependency: one client per process, not one per request.

    Cached so connections are pooled across requests rather than
    reconnecting every time — `httpx.AsyncClient` is explicitly
    designed to be reused this way. Tests override this via FastAPI's
    `dependency_overrides`, never by patching this function's
    internals (CLAUDE.md's dependency-injection rule).
    """
    return build_upstream_client(get_settings())
