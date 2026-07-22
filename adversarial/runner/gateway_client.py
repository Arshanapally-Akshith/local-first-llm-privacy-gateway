"""A capturing stand-in for the upstream HTTP client, shared by every
test and runner that needs to see exactly what "crossed the wire" to
the upstream provider — not just what the mock chose to echo back.

Promoted here from three near-identical private copies
(`tests/integration/test_sanitize_integration.py`,
`test_phase_3_gate.py`, `test_phase_4_gate.py` each defined their own
`_CapturingTransport` + `_override_with_capturing_mock_upstream()`
before this module existed — CLAUDE.md's refactor policy: "twice is a
coincidence; three times is a refactor"). Lives under
`adversarial/runner/`, not `tests/`, because this suite's own runner
(`adversarial/runner/run.py`, invoked as a standalone script by
`make adversarial`, not by pytest) needs the identical mechanism as
its core execution strategy, not merely as test scaffolding — `src/`'s
own layering rule ("tests import production code, never the reverse")
would be inverted if this lived under `tests/` and the runner imported
it from there. The three existing test modules now import it from
here instead of defining their own copy; behaviour is unchanged.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import httpx
from fastapi import FastAPI

from src.proxy.upstream_client import get_upstream_client


class CapturingTransport(httpx.AsyncBaseTransport):
    """Wraps a real transport (typically `httpx.ASGITransport(app=mock_app)`)
    and records every request body that passes through it."""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        self._inner = inner
        self.captured_bodies: list[bytes] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.captured_bodies.append(request.content)
        return await self._inner.handle_async_request(request)


def override_with_capturing_mock_upstream(app: FastAPI, mock_app: FastAPI) -> CapturingTransport:
    """Point `app`'s upstream-client dependency at `mock_app` through a
    fresh `CapturingTransport`, and return it so the caller can inspect
    `.captured_bodies` afterward.

    Does not clear the override itself — callers own that (via a
    pytest fixture, or `capturing_mock_upstream()`'s own context-manager
    cleanup below), mirroring `app.dependency_overrides`' own manual,
    caller-owned lifecycle everywhere else it's used in this codebase.
    """
    capturing = CapturingTransport(httpx.ASGITransport(app=mock_app))

    def _get_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=capturing, base_url="http://mock-upstream")

    app.dependency_overrides[get_upstream_client] = _get_client
    return capturing


@contextmanager
def capturing_mock_upstream(app: FastAPI, mock_app: FastAPI) -> Iterator[CapturingTransport]:
    """Context-manager form for non-pytest callers (the runner): installs
    the override, yields the `CapturingTransport`, and always removes
    the override on exit — the runner has no pytest fixture to do this
    for it, and a leaked override would make every subsequent case in
    the same process silently share one case's captured bodies.
    """
    capturing = override_with_capturing_mock_upstream(app, mock_app)
    try:
        yield capturing
    finally:
        app.dependency_overrides.pop(get_upstream_client, None)
