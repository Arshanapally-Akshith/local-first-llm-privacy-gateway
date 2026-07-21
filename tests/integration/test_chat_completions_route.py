"""Integration tests for the gateway's /v1/chat/completions route.

Most tests override the upstream client dependency to route through
httpx.ASGITransport pointed directly at the mock upstream's ASGI app —
exercising the full gateway -> mock pipeline in-process, no real
sockets, no two-process setup. Failure-mode tests use
httpx.MockTransport to simulate connection errors, timeouts, and
malformed responses deterministically, without needing a real
unreachable host or a real slow one.
"""

import json
from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from src.mock_upstream.main import app as mock_app
from src.proxy.upstream_client import get_upstream_client


def _override_with_mock_upstream() -> None:
    def _get_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mock_app), base_url="http://mock-upstream"
        )

    app.dependency_overrides[get_upstream_client] = _get_client


def _override_with_transport(transport: httpx.MockTransport) -> None:
    def _get_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport, base_url="http://mock-upstream")

    app.dependency_overrides[get_upstream_client] = _get_client


@pytest.fixture(autouse=True)
def _clear_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.pop(get_upstream_client, None)


def _parse_sse_content(raw: str) -> str:
    """Reassemble content from the gateway's own SSE output."""
    content = ""
    for line in raw.splitlines():
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        obj = json.loads(line[len("data: ") :])
        delta = obj["choices"][0]["delta"]
        content += delta.get("content", "")
    return content


def test_non_streaming_forwards_and_returns_upstream_body() -> None:
    _override_with_mock_upstream()
    client = TestClient(app)

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "Hello world"}],
            "stream": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "Hello world"


def test_streaming_reassembles_content_byte_identical() -> None:
    _override_with_mock_upstream()
    client = TestClient(app)

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "ABCDE1234F"}],
            "stream": True,
        },
    )

    assert response.status_code == 200
    assert response.text.rstrip().endswith("data: [DONE]")
    assert _parse_sse_content(response.text) == "ABCDE1234F"


def test_streaming_with_pathological_chunking_still_reassembles() -> None:
    """The BUILD.md Phase 1 Gate scenario: mock forced to split a known
    string across many chunks; gateway output must still be correct."""
    _override_with_mock_upstream()
    client = TestClient(app)

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "ABCDE1234F was approved"}],
            "stream": True,
            "chunking": {"n": 15},
        },
    )

    assert _parse_sse_content(response.text) == "ABCDE1234F was approved"


def test_non_streaming_connection_failure_returns_502() -> None:
    def _raise_connect_error(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _override_with_transport(httpx.MockTransport(_raise_connect_error))
    client = TestClient(app)

    response = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": False},
    )

    assert response.status_code == 502


def test_non_streaming_timeout_returns_504() -> None:
    def _raise_timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    _override_with_transport(httpx.MockTransport(_raise_timeout))
    client = TestClient(app)

    response = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": False},
    )

    assert response.status_code == 504


def test_streaming_connection_failure_also_returns_502() -> None:
    """The connect attempt happens before StreamingResponse is
    returned, so this can still become a real error status."""

    def _raise_connect_error(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _override_with_transport(httpx.MockTransport(_raise_connect_error))
    client = TestClient(app)

    response = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": True},
    )

    assert response.status_code == 502


def test_malformed_streaming_response_terminates_stream_honestly_not_as_an_error_status() -> None:
    """Malformed data discovered mid-stream cannot become an error
    status — the 200 is already committed by the time it's found. It
    must still terminate cleanly with [DONE], not crash or hang."""

    def _return_garbage_sse(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b"data: not valid json at all\n\n",
        )

    _override_with_transport(httpx.MockTransport(_return_garbage_sse))
    client = TestClient(app)

    response = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": True},
    )

    assert response.status_code == 200
    assert response.text.rstrip().endswith("data: [DONE]")


def test_upstream_4xx_propagated_verbatim_non_streaming() -> None:
    def _return_400(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "bad request"}})

    _override_with_transport(httpx.MockTransport(_return_400))
    client = TestClient(app)

    response = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": False},
    )

    assert response.status_code == 400
    assert response.json() == {"error": {"message": "bad request"}}


@pytest.mark.parametrize("malformed_body", [[1, 2, 3], "just a string", 42])
def test_non_object_json_body_returns_400_not_a_crash(malformed_body: object) -> None:
    """Regression: sanitize() assumes a JSON-object body and previously
    had no validation ahead of it. A syntactically valid but non-object
    top-level body (array/string/number) parses fine via
    `request.json()`, then reached `sanitize()` -> `field_walker.walk()`
    -> (for a bare string) ran real detection/FF1 over it -> an
    unchecked `assert isinstance(sanitized, dict)` -> an unhandled
    AssertionError -> a generic 500, never reaching the upstream client
    override below (proving it, not just asserting the status code)."""
    client = TestClient(app)

    response = client.post("/v1/chat/completions", json=malformed_body)

    assert response.status_code == 400
