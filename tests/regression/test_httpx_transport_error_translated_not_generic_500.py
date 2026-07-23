"""Regression test for the Phase 7 failure-path audit finding: only
`httpx.TimeoutException` and `httpx.ConnectError` were caught at
connection-open time (`src/proxy/routes.py`). A `httpx.ReadError` —
a `TransportError` sibling of `ConnectError`, not caught by the old,
narrower clause — fell through to a generic, unstructured 500 at
connection-open, inconsistent with the exact same exception class
already being handled gracefully once inside the SSE generator's own
mid-stream loop (`routes.py`'s `except (httpx.TransportError,
UpstreamError)`).

Fixed by widening the connection-open catch to `httpx.TransportError`
(`_translate_upstream_connection_failure`). `tests/unit/
test_upstream_connection_translation.py` covers every `TransportError`
category exhaustively at the unit level; this is the named, symptom-
anchored regression proof at the real HTTP layer, non-streaming.
"""

import httpx
from fastapi.testclient import TestClient

from app.main import app
from src.proxy.upstream_client import get_upstream_client


def test_read_error_at_connection_open_returns_502_not_a_generic_500() -> None:
    def _raise_read_error(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadError("connection reset by peer")

    def _get_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.MockTransport(_raise_read_error), base_url="http://mock-upstream"
        )

    app.dependency_overrides[get_upstream_client] = _get_client
    try:
        client = TestClient(app, headers={"X-Session-Id": "test-session-1"})

        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False,
            },
        )

        assert response.status_code == 502
        assert response.json() == {"error": "could not connect to upstream"}
    finally:
        app.dependency_overrides.pop(get_upstream_client, None)
