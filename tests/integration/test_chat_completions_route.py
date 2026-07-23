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
import logging
from collections.abc import Iterator, Sequence

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from src.core.clock import get_clock
from src.core.fail_mode import FailMode, get_fail_mode
from src.core.types import Offset, SessionId
from src.detect.tier2.gliner_model import get_tier2_model
from src.detect.tier2.model import ModelEntityMatch
from src.mock_upstream.main import app as mock_app
from src.proxy.upstream_client import get_upstream_client
from src.session.store import get_session_store


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


class _RaisingTier2Model:
    """Phase 4 Task 4: a Tier-2 model that always fails, to prove
    `FAIL_MODE`'s HTTP-level behaviour end-to-end — `app/main.py`'s
    `FailClosedError` -> 503 handler, exercised for real rather than
    only at the `cascade.detect()`/`sanitize()` unit level."""

    def find_entities(self, text: str) -> Sequence[ModelEntityMatch]:
        raise RuntimeError("model process crashed")


def _override_tier2_model_to_always_fail() -> None:
    app.dependency_overrides[get_tier2_model] = _RaisingTier2Model


class _FixedMatchesTier2Model:
    """Phase 4 Task 5: a Tier-2 model returning a fixed set of matches,
    filtered to whichever ones fit the `text` a given call receives —
    same reasoning as `test_sanitize.py`'s own fake (this route's
    `sanitize()` call walks multiple body fields, not just the one the
    test cares about)."""

    def __init__(self, matches: Sequence[ModelEntityMatch]) -> None:
        self._matches = matches

    def find_entities(self, text: str) -> Sequence[ModelEntityMatch]:
        return [m for m in self._matches if m.end <= len(text)]


def _override_tier2_model_with_matches(matches: Sequence[ModelEntityMatch]) -> None:
    app.dependency_overrides[get_tier2_model] = lambda: _FixedMatchesTier2Model(matches)


def _override_fail_mode(mode: FailMode) -> None:
    app.dependency_overrides[get_fail_mode] = lambda: mode


@pytest.fixture(autouse=True)
def _clear_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.pop(get_upstream_client, None)
    app.dependency_overrides.pop(get_fail_mode, None)


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
    client = TestClient(app, headers={"X-Session-Id": "test-session-1"})

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
    client = TestClient(app, headers={"X-Session-Id": "test-session-1"})

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
    client = TestClient(app, headers={"X-Session-Id": "test-session-1"})

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
    client = TestClient(app, headers={"X-Session-Id": "test-session-1"})

    response = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": False},
    )

    assert response.status_code == 502


def test_non_streaming_timeout_returns_504() -> None:
    def _raise_timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    _override_with_transport(httpx.MockTransport(_raise_timeout))
    client = TestClient(app, headers={"X-Session-Id": "test-session-1"})

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
    client = TestClient(app, headers={"X-Session-Id": "test-session-1"})

    response = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": True},
    )

    assert response.status_code == 502


@pytest.mark.parametrize(
    "raise_exc",
    [
        httpx.ReadError("connection reset by peer"),
        httpx.RemoteProtocolError("server sent invalid HTTP response"),
    ],
)
def test_non_streaming_transport_error_returns_502_not_a_generic_500(
    raise_exc: httpx.TransportError,
) -> None:
    """Phase 7 hardening: previously only httpx.TimeoutException and
    httpx.ConnectError were caught at connection-open time. A
    ReadError/RemoteProtocolError here fell through to a generic,
    unstructured 500 — inconsistent with the exact same exception
    classes already being handled gracefully once inside the SSE
    generator's own loop. Widening to httpx.TransportError closes that
    gap; see src/proxy/routes.py::_translate_upstream_connection_failure."""

    def _raise(request: httpx.Request) -> httpx.Response:
        raise raise_exc

    _override_with_transport(httpx.MockTransport(_raise))
    client = TestClient(app, headers={"X-Session-Id": "test-session-1"})

    response = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": False},
    )

    assert response.status_code == 502
    assert response.json() == {"error": "could not connect to upstream"}


@pytest.mark.parametrize(
    "raise_exc",
    [
        httpx.ReadError("connection reset by peer"),
        httpx.RemoteProtocolError("server sent invalid HTTP response"),
    ],
)
def test_streaming_transport_error_at_connect_returns_502_not_a_generic_500(
    raise_exc: httpx.TransportError,
) -> None:
    """The streaming counterpart of the test above — the connect
    attempt happens before StreamingResponse is returned, so this can
    still become a real error status, exactly like ConnectError already
    does (test_streaming_connection_failure_also_returns_502)."""

    def _raise(request: httpx.Request) -> httpx.Response:
        raise raise_exc

    _override_with_transport(httpx.MockTransport(_raise))
    client = TestClient(app, headers={"X-Session-Id": "test-session-1"})

    response = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": True},
    )

    assert response.status_code == 502
    assert response.json() == {"error": "could not connect to upstream"}


def test_rehydration_invariant_violation_returns_500_with_structured_error_body() -> None:
    """Phase 7 hardening (GatewayError catch-all): deliberately
    construct the same invariant-violation state
    tests/unit/test_rehydrate.py's own unit test constructs — a
    session's known-surrogate registry says PERSON for a value with no
    matching reverse-map entry — but through the real HTTP route,
    non-streaming. Previously this reached Starlette's bare,
    unstructured default 500; now it gets the same `{"error": ...}`
    shape every other GatewayError subclass already had."""

    def _echo_unmapped_surrogate(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "x",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": "Noted, Someone Nobody Allocated.",
                        },
                    }
                ],
            },
        )

    _override_with_transport(httpx.MockTransport(_echo_unmapped_surrogate))
    session_id = "rehydration-invariant-violation-session"
    session = get_session_store().get_or_create(SessionId(session_id))
    session.record_surrogate("Someone Nobody Allocated", "PERSON", get_clock().now())
    client = TestClient(app, headers={"X-Session-Id": session_id})

    response = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": False},
    )

    assert response.status_code == 500
    assert "error" in response.json()


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
    client = TestClient(app, headers={"X-Session-Id": "test-session-1"})

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
    client = TestClient(app, headers={"X-Session-Id": "test-session-1"})

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
    client = TestClient(app, headers={"X-Session-Id": "test-session-1"})

    response = client.post("/v1/chat/completions", json=malformed_body)

    assert response.status_code == 400


def test_missing_session_id_header_returns_400() -> None:
    """Phase 3 architectural decision: explicit required session header,
    fail closed if missing — no derived/implicit session identity."""
    client = TestClient(app)  # deliberately no X-Session-Id default here

    response = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": False},
    )

    assert response.status_code == 400


def test_empty_session_id_header_returns_400() -> None:
    client = TestClient(app, headers={"X-Session-Id": ""})

    response = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": False},
    )

    assert response.status_code == 400


def test_tier2_failure_under_fail_mode_closed_returns_503() -> None:
    """Phase 4 Task 4's HTTP-level proof: `app/main.py`'s
    `FailClosedError` handler actually maps a real Tier-2 failure to a
    503, end-to-end through the real route — not just at the
    `cascade.detect()`/`sanitize()` unit level."""
    _override_with_mock_upstream()
    _override_tier2_model_to_always_fail()
    _override_fail_mode("closed")
    client = TestClient(app, headers={"X-Session-Id": "test-session-1"})

    response = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": False},
    )

    assert response.status_code == 503


def test_tier2_failure_under_fail_mode_open_still_returns_200() -> None:
    """The counterpart of the test above: the same Tier-2 failure, under
    `open`, must not take the request down — it forwards with whatever
    Tier 1 alone found."""
    _override_with_mock_upstream()
    _override_tier2_model_to_always_fail()
    _override_fail_mode("open")
    client = TestClient(app, headers={"X-Session-Id": "test-session-2"})

    response = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": False},
    )

    assert response.status_code == 200


def test_person_span_round_trips_through_the_full_http_request_response_cycle() -> None:
    """Phase 4 Task 5's own end-to-end proof: a detected `PERSON` span
    is substituted with a name-map surrogate before the mock upstream
    ever sees it, the mock echoes that surrogate back (it only ever
    sees what the gateway sent), and the caller receives the *real*
    name back — the same round-trip `test_rehydrate_integration.py`
    already proves for Tier-1 (FF1) entities, now proven for a Tier-2
    name-map entity for the first time."""
    _override_with_mock_upstream()
    content = "Ramesh Kumar called yesterday"
    person_start = content.index("Ramesh Kumar")
    person_end = person_start + len("Ramesh Kumar")
    _override_tier2_model_with_matches(
        [ModelEntityMatch(start=Offset(person_start), end=Offset(person_end), entity_type="PERSON")]
    )
    client = TestClient(app, headers={"X-Session-Id": "test-session-person-roundtrip"})

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4",
            "messages": [{"role": "user", "content": content}],
            "stream": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == content


def test_non_streaming_response_carries_x_correlation_id_header() -> None:
    """Phase 7: the latency harness drives the gateway as a real
    subprocess over real sockets, not in-process — this header is the
    only way it can match a response it just received back to that
    request's own structured log lines (see
    src/proxy/routes.py::_CORRELATION_ID_HEADER)."""
    _override_with_mock_upstream()
    client = TestClient(app, headers={"X-Session-Id": "test-session-1"})

    response = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": False},
    )

    assert response.status_code == 200
    correlation_id = response.headers.get("x-correlation-id")
    assert correlation_id
    assert len(correlation_id) > 0


def test_streaming_response_carries_x_correlation_id_header() -> None:
    _override_with_mock_upstream()
    client = TestClient(app, headers={"X-Session-Id": "test-session-1"})

    response = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": True},
    )

    assert response.status_code == 200
    assert response.headers.get("x-correlation-id")


def test_streaming_emits_upstream_first_chunk_and_window_first_release_once(
    captured_records: list[logging.LogRecord],
) -> None:
    """Phase 7 instrumentation: exactly one `latency.upstream_first_chunk`
    and one `latency.window_first_release` event per streamed response,
    both carrying the same `correlation_id` as the response's own
    `X-Correlation-Id` header and a numeric `timestamp_ms` — what
    `latency/runner/log_capture.py` depends on to compute the window's
    TTFT tax."""
    _override_with_mock_upstream()
    client = TestClient(app, headers={"X-Session-Id": "test-session-1"})

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "hello there"}],
            "stream": True,
        },
    )

    assert response.status_code == 200
    correlation_id = response.headers["x-correlation-id"]

    upstream_events = [
        r for r in captured_records if getattr(r, "event", None) == "latency.upstream_first_chunk"
    ]
    release_events = [
        r for r in captured_records if getattr(r, "event", None) == "latency.window_first_release"
    ]
    assert len(upstream_events) == 1
    assert len(release_events) == 1
    assert upstream_events[0].correlation_id == correlation_id  # type: ignore[attr-defined]
    assert release_events[0].correlation_id == correlation_id  # type: ignore[attr-defined]
    assert isinstance(upstream_events[0].timestamp_ms, float)  # type: ignore[attr-defined]
    assert isinstance(release_events[0].timestamp_ms, float)  # type: ignore[attr-defined]
    # The window can only release what upstream already sent it.
    assert release_events[0].timestamp_ms >= upstream_events[0].timestamp_ms  # type: ignore[attr-defined]


def test_non_streaming_request_emits_neither_latency_event(
    captured_records: list[logging.LogRecord],
) -> None:
    """The two new events are streaming-only (TTFT has no meaning for a
    single blocking response) — a non-streaming request must not emit
    either one."""
    _override_with_mock_upstream()
    client = TestClient(app, headers={"X-Session-Id": "test-session-1"})

    client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": False},
    )

    events = {getattr(r, "event", None) for r in captured_records}
    assert "latency.upstream_first_chunk" not in events
    assert "latency.window_first_release" not in events
