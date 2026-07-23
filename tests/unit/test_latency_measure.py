"""Unit tests for the Phase 7 timeout/error-handling fixes in
`latency/runner/measure.py` — a per-request timeout, transport
failure, or gateway-generated HTTP 504 upstream-timeout must become a
recorded outcome (`_RawFailure`), never a raised exception that would
abort the whole benchmark run (see `docs/DECISIONS.md`, 2026-07-23,
"Phase 7 Task 2 follow-up" and "Phase 7 Task 2 second follow-up").
Every other non-200 status must still raise, unchanged.
"""

import httpx
import pytest

from latency.runner import measure
from latency.runner.measure import (
    CellRawResults,
    _RawFailure,
    _RawSuccess,
    _send_one,
    run_cell,
)
from latency.workloads.definitions import BASELINE_CLEAN

_SSE_BODY = b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\ndata: [DONE]\n\n'


def _mock_client(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler, base_url="http://mock-gateway")


def test_send_one_returns_timeout_failure_on_read_timeout() -> None:
    def _raise_read_timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated read timeout", request=request)

    client = _mock_client(httpx.MockTransport(_raise_read_timeout))

    outcome = _send_one(client, BASELINE_CLEAN, "session-1")

    assert isinstance(outcome, _RawFailure)
    assert outcome.kind == "timeout"


def test_send_one_returns_timeout_failure_on_connect_timeout() -> None:
    def _raise_connect_timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("simulated connect timeout", request=request)

    client = _mock_client(httpx.MockTransport(_raise_connect_timeout))

    outcome = _send_one(client, BASELINE_CLEAN, "session-1")

    assert isinstance(outcome, _RawFailure)
    assert outcome.kind == "timeout"


def test_send_one_returns_error_failure_on_connection_reset() -> None:
    """A non-timeout transport failure (e.g. connection reset under
    heavy concurrent load) is also a recorded outcome, distinct from a
    timeout -- both are non-fatal, but distinguishable in the report."""

    def _raise_connect_error(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated connection reset", request=request)

    client = _mock_client(httpx.MockTransport(_raise_connect_error))

    outcome = _send_one(client, BASELINE_CLEAN, "session-1")

    assert isinstance(outcome, _RawFailure)
    assert outcome.kind == "error"


def test_send_one_raises_on_non_200_response() -> None:
    """A non-200 response for a fixed, known-good workload is a real
    defect, not a legitimate benchmark outcome -- must still raise,
    unlike a timeout/transport failure."""

    def _return_500(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"internal error")

    client = _mock_client(httpx.MockTransport(_return_500))

    with pytest.raises(RuntimeError, match="got HTTP 500"):
        _send_one(client, BASELINE_CLEAN, "session-1")


def test_send_one_raises_when_correlation_header_missing() -> None:
    def _return_without_header(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_SSE_BODY)

    client = _mock_client(httpx.MockTransport(_return_without_header))

    with pytest.raises(RuntimeError, match="carried no"):
        _send_one(client, BASELINE_CLEAN, "session-1")


def test_send_one_returns_success_on_normal_response() -> None:
    def _return_ok(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"x-correlation-id": "corr-1"}, content=_SSE_BODY
        )

    client = _mock_client(httpx.MockTransport(_return_ok))

    outcome = _send_one(client, BASELINE_CLEAN, "session-1")

    assert isinstance(outcome, _RawSuccess)
    assert outcome.correlation_id == "corr-1"


def test_send_one_classifies_gateway_504_upstream_timeout_as_a_timeout_outcome() -> None:
    """The exact, structured 504
    `src/proxy/routes.py::_translate_upstream_connection_failure` emits
    for the gateway's own upstream-client timeout -- observed for real
    on `multiturn_5` at concurrency=16 (`docs/DECISIONS.md`, 2026-07-23,
    "Phase 7 Task 2 second follow-up") -- must become a recorded
    timeout outcome, not a fatal RuntimeError."""

    def _return_gateway_upstream_timeout(request: httpx.Request) -> httpx.Response:
        return httpx.Response(504, json={"error": "upstream request timed out"})

    client = _mock_client(httpx.MockTransport(_return_gateway_upstream_timeout))

    outcome = _send_one(client, BASELINE_CLEAN, "session-1")

    assert isinstance(outcome, _RawFailure)
    assert outcome.kind == "timeout"


@pytest.mark.parametrize("status_code", [400, 422, 500, 502, 503])
def test_send_one_still_raises_on_every_other_non_200_status(status_code: int) -> None:
    """Deliberately not generalized past the one specific, content-
    verified 504 shape: 400/422/500/502/503 (and, by the next test, an
    unrecognized 504) all represent a defect or infrastructure problem
    for a fixed, known-good workload, not the expected scalability
    behaviour this phase measures, and must stay fatal."""

    def _return_status(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": "something else entirely"})

    client = _mock_client(httpx.MockTransport(_return_status))

    with pytest.raises(RuntimeError, match=f"got HTTP {status_code}"):
        _send_one(client, BASELINE_CLEAN, "session-1")


def test_send_one_raises_on_a_504_with_an_unrecognized_body() -> None:
    """A 504 that isn't *exactly* the known upstream-timeout shape must
    not be silently reclassified as that specific, already-understood
    outcome -- matched by content, not status code alone."""

    def _return_different_504(request: httpx.Request) -> httpx.Response:
        return httpx.Response(504, json={"error": "some other gateway timeout condition"})

    client = _mock_client(httpx.MockTransport(_return_different_504))

    with pytest.raises(RuntimeError, match="got HTTP 504"):
        _send_one(client, BASELINE_CLEAN, "session-1")


def test_send_one_raises_on_a_504_with_a_non_json_body() -> None:
    def _return_504_plain_text(request: httpx.Request) -> httpx.Response:
        return httpx.Response(504, content=b"Gateway Timeout")

    client = _mock_client(httpx.MockTransport(_return_504_plain_text))

    with pytest.raises(RuntimeError, match="got HTTP 504"):
        _send_one(client, BASELINE_CLEAN, "session-1")


def test_run_cell_excludes_failures_from_measurements_and_counts_them(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Drives `run_cell()`'s own aggregation logic directly (not
    `_send_one`'s classification, covered above) by faking `_send_one`
    with a deterministic, session-id-keyed outcome -- avoids any shared
    mutable state across the real `ThreadPoolExecutor` worker threads.
    """
    outcomes: list[measure.RequestOutcome] = [
        _RawSuccess("corr-0", 0.0, 10.0, 20.0),
        _RawFailure("timeout", "simulated timeout"),
        _RawSuccess("corr-2", 0.0, 15.0, 25.0),
        _RawFailure("error", "simulated connection reset"),
    ]

    def _fake_send_one(
        client: httpx.Client, workload: object, session_id: str
    ) -> measure.RequestOutcome:
        index = int(session_id.rsplit("-", 1)[-1])
        return outcomes[index]

    monkeypatch.setattr(measure, "_send_one", _fake_send_one)
    log_path = tmp_path / "gateway_stderr.log"
    log_path.write_text("", encoding="utf-8")

    raw = run_cell(
        "http://127.0.0.1:1",
        log_path,
        BASELINE_CLEAN,
        concurrency=2,
        total_requests=4,
        warmup_requests=0,
        session_id_prefix="test",
    )

    assert isinstance(raw, CellRawResults)
    assert raw.attempted == 4
    assert len(raw.measurements) == 2
    assert {m.correlation_id for m in raw.measurements} == {"corr-0", "corr-2"}
    assert raw.timeout_count == 1
    assert raw.error_count == 1


def test_run_cell_warmup_discard_applies_by_submission_index_not_success(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Warm-up discard must be positional (the first N *submitted*
    requests), regardless of which ones happened to succeed or fail --
    otherwise a timeout among the warm-up requests would silently shift
    which repetitions get measured."""
    outcomes: list[measure.RequestOutcome] = [
        _RawFailure("timeout", "warmup request that timed out"),
        _RawSuccess("corr-1", 0.0, 10.0, 20.0),
        _RawSuccess("corr-2", 0.0, 12.0, 22.0),
    ]

    def _fake_send_one(
        client: httpx.Client, workload: object, session_id: str
    ) -> measure.RequestOutcome:
        index = int(session_id.rsplit("-", 1)[-1])
        return outcomes[index]

    monkeypatch.setattr(measure, "_send_one", _fake_send_one)
    log_path = tmp_path / "gateway_stderr.log"
    log_path.write_text("", encoding="utf-8")

    raw = run_cell(
        "http://127.0.0.1:1",
        log_path,
        BASELINE_CLEAN,
        concurrency=1,
        total_requests=3,
        warmup_requests=1,
        session_id_prefix="test",
    )

    assert raw.attempted == 2
    assert raw.timeout_count == 0
    assert {m.correlation_id for m in raw.measurements} == {"corr-1", "corr-2"}
