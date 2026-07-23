"""Fires a fixed number of requests at a given concurrency level for a
given workload against a real, running gateway
(`process_harness.ManagedProcess`), over real sockets, and combines
each request's client-observed timing with the gateway's own internal
log-derived timing (`log_capture.py`) into one `RequestMeasurement` per
request.

Concurrency is enforced with a plain `concurrent.futures.ThreadPoolExecutor`
bounded at `concurrency` workers — no new dependency (stdlib plus the
already-present `httpx`), and exactly the mechanism needed: submitting
every repetition up front to a pool bounded at N workers keeps N
requests genuinely in flight at once against the real subprocess, which
is the actual phenomenon BUILD.md's Phase 7 names ("Python GIL + CPU
inference at 4 concurrent requests is a different distribution
entirely").

A per-request timeout or transient transport failure is a *measured
outcome* of a (workload, concurrency) cell, not a fatal harness error —
see `RequestOutcome` and `CellRawResults` below. A pilot run against
`multiturn_5` at concurrency=8 hit the previous fixed 60s timeout and
took the entire run down with it; `docs/DECISIONS.md` (2026-07-23,
"Phase 7 Task 2 follow-up") records the investigation and the fix
implemented here.

A *second* pilot run, after that fix, reached `multiturn_5` at
concurrency=16 and got a gateway-generated HTTP 504
(`{"error": "upstream request timed out"}` —
`src/proxy/routes.py::_translate_upstream_connection_failure`) rather
than a client-side `httpx` exception: the gateway's own upstream-client
timeout (`UPSTREAM_TIMEOUT`, default 30s — a *different, inner* timeout
than this module's own client-to-gateway one) tripped first once the
outer timeout was widened. `docs/DECISIONS.md` (2026-07-23, "Phase 7
Task 2 second follow-up") records that investigation and the narrow fix
below: only this exact, structured 504 becomes a recorded timeout
outcome. Every other non-200 status — 400, 422, 500, 502, 503, or
anything else unexpected — stays a fatal `RuntimeError`, deliberately
not generalized, because those represent a defect or an infrastructure
problem, not the expected scalability behaviour this phase measures.
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

import httpx

from latency.runner.log_capture import (
    RequestLogRecord,
    classify_tier_hit,
    index_by_correlation_id,
    window_tax_ms,
    window_tax_percent,
)
from latency.workloads.workload_types import LatencyWorkload

_CHAT_COMPLETIONS_PATH: str = "/v1/chat/completions"
_SESSION_ID_HEADER: str = "X-Session-Id"
_CORRELATION_ID_HEADER: str = "x-correlation-id"
"""Lowercase: `httpx.Headers` is case-insensitive on lookup, but
spelling it lowercase here documents that this is reading the response
header `src/proxy/routes.py::_CORRELATION_ID_HEADER` sets (`X-Correlation-Id`),
not asserting anything about wire casing."""

_GATEWAY_UPSTREAM_TIMEOUT_STATUS: Final[int] = 504
_GATEWAY_UPSTREAM_TIMEOUT_BODY: Final[dict[str, str]] = {"error": "upstream request timed out"}
"""The exact status and body `_translate_upstream_connection_failure()`
(`src/proxy/routes.py`) produces for a gateway-side upstream-client
timeout (`Settings.upstream_timeout`, a different, *inner* timeout from
this module's own client-to-gateway `DEFAULT_REQUEST_TIMEOUT_S`) —
observed for real on `multiturn_5` at concurrency=16 (`docs/DECISIONS.md`,
2026-07-23, "Phase 7 Task 2 second follow-up"). Matched by *content*,
not status code alone: a 504 that doesn't carry this exact body is
still an unexpected, fatal condition, not silently reclassified as
this specific, already-understood outcome. Deliberately narrow, per
explicit instruction: every other non-200 status — 400, 422, 500, 502,
503, or anything else unexpected — stays fatal."""


def _is_gateway_upstream_timeout(response: httpx.Response, body: bytes) -> bool:
    if response.status_code != _GATEWAY_UPSTREAM_TIMEOUT_STATUS:
        return False
    try:
        parsed: object = json.loads(body)
    except json.JSONDecodeError:
        return False
    return bool(parsed == _GATEWAY_UPSTREAM_TIMEOUT_BODY)

DEFAULT_REQUEST_TIMEOUT_S: Final[float] = 120.0
"""Per-request `httpx` timeout — connect, read, write, and pool all set
to this one value (`httpx.Client(timeout=...)`'s scalar-timeout
expansion), applied uniformly to every workload and concurrency level.

120s, not the original 60s that a real pilot run tripped
(`multiturn_5` at concurrency=8 — see `docs/DECISIONS.md`, 2026-07-23,
"Phase 7 Task 2 follow-up"). The root cause is not this constant: it is
that `chat_completions()` (`src/proxy/routes.py`) calls `sanitize()`
synchronously, inline, with no thread/executor offload, inside a
single-process, single-event-loop `uvicorn` server — every concurrently
-connected request's detection work fully serializes on that one event
loop, so a request's true wait time scales with how many *other*
requests are already queued ahead of it, not just its own cost. 120s is
a considered starting point given the pilot's own concurrency=1/4
measurements (several workloads already cost multiple seconds per
request *before* any queueing is added), not a value expected to
survive every workload/concurrency/repetition-count combination in the
matrix — which is exactly why a timeout is a *recorded per-cell
outcome* (`RequestOutcome`, `CellRawResults.timeout_count`) rather than
a fatal error: no single constant here can be "big enough" for all 40
cells at n=200, and this harness should not pretend otherwise by
guessing a bigger number and hoping. Overridable per run via
`python -m latency.runner.run --request-timeout SECONDS`
(`latency/runner/run.py`) for whichever direction the default proves
wrong in.

Per CLAUDE.md's Forbidden Actions ("no architecture change without
approval") and this task's own explicit instruction: the serialization
behaviour itself is not touched here. This value, and the outcome-
recording mechanism below, only change how the harness *measures and
reports* that behaviour — never the gateway's own concurrency model.
"""

_LOG_SETTLE_DELAY_S: float = 0.1
"""A short, explicitly-not-a-measurement settle delay before reading
back the gateway's captured log file at the end of a batch:
`logging.StreamHandler.emit()` flushes after every write, so this is
pure insurance against OS-level file-visibility latency between the
child process's write and this process's read of the same file --
never counted as part of any reported metric."""


@dataclass(frozen=True, slots=True)
class RequestMeasurement:
    """One *successful* request's fully combined measurement — client-
    observed timing plus the gateway's own internal log-derived timing,
    joined by `correlation_id`. A timed-out or transport-failed request
    never becomes one of these — see `_RawFailure` and
    `CellRawResults` instead.
    """

    correlation_id: str
    client_ttft_ms: float
    """Wall-clock time from just before sending the request to the
    first byte read off the real socket — the primary, human-perceived
    TTFT number (Phase 7 design). Every workload in
    `latency/workloads/definitions.py` streams, so this is always
    populated; a non-streaming workload would have no meaningful TTFT
    at all and is out of this phase's fixed workload matrix."""
    client_total_latency_ms: float
    ttft_without_window_ms: float | None
    window_tax_ms: float | None
    window_tax_percent: float | None
    tier_hit_class: str


@dataclass(frozen=True, slots=True)
class _RawSuccess:
    correlation_id: str
    request_sent_at_ms: float
    client_ttft_ms: float
    client_total_latency_ms: float


@dataclass(frozen=True, slots=True)
class _RawFailure:
    """A request that did not complete — recorded, never raised past
    `_send_one`. `kind` distinguishes a timeout (this cell's own
    request-timeout ceiling was reached — informative about load, not
    about breakage) from a lower-level transport error (connection
    reset, and similar — rarer, but equally not worth crashing an
    otherwise-unrelated 40-cell run over).
    """

    kind: Literal["timeout", "error"]
    detail: str


RequestOutcome = _RawSuccess | _RawFailure


@dataclass(frozen=True, slots=True)
class CellRawResults:
    """Everything one `run_cell()` call produces: the successful
    requests' full measurements, plus how many of the *measured*
    (post-warmup) requests timed out or otherwise failed to complete.

    `attempted` is `measurements` plus every failure — i.e. the total
    number of post-warmup requests this cell actually tried, which can
    be less than the cell's own `total_requests - warmup_requests` only
    if the harness itself was interrupted; it is always exactly that
    value in ordinary operation, since every submitted future is waited
    on via `future.result()` regardless of outcome.
    """

    measurements: list[RequestMeasurement]
    attempted: int
    timeout_count: int
    error_count: int


def _send_one(client: httpx.Client, workload: LatencyWorkload, session_id: str) -> RequestOutcome:
    """Send one streaming request over a real socket and time it from
    the client's own perspective.

    Returns a `_RawFailure` (never raises) for:
      - a timeout (`httpx.TimeoutException` — connect, read, write, or
        pool) or any other transport-level failure (`httpx.TransportError`
        — e.g. a connection reset under heavy concurrent load) on this
        module's own client-to-gateway connection;
      - a gateway-generated HTTP 504 carrying exactly
        `_GATEWAY_UPSTREAM_TIMEOUT_BODY` — the gateway's *own*
        upstream-client timeout (`Settings.upstream_timeout`) tripping
        under the same concurrent load, translated into a real HTTP
        response by `src/proxy/routes.py`'s existing error handling
        rather than a raw client-side exception.
    All three are legitimate, reportable outcomes of a (workload,
    concurrency) cell on this machine, not harness defects (Phase 7
    design follow-up; see this module's own docstring).

    Raises:
        RuntimeError: any other non-200 response (400, 422, 500, 502,
            503, an unrecognized 504, or anything else unexpected), or
            a 200 response missing the `X-Correlation-Id` header.
            Deliberately not generalized past the one specific,
            content-verified 504 shape above: these represent a defect
            or an infrastructure problem for a fixed, known-good
            workload, not the expected scalability behaviour this phase
            measures, and must never be confused with "the gateway is
            just slow right now."
    """
    request_sent_at_ms = time.time() * 1000
    start = time.perf_counter()
    client_ttft_ms: float | None = None
    try:
        with client.stream(
            "POST",
            _CHAT_COMPLETIONS_PATH,
            json=workload.request_body,
            headers={_SESSION_ID_HEADER: session_id},
        ) as response:
            if response.status_code != 200:
                body = response.read()
                if _is_gateway_upstream_timeout(response, body):
                    return _RawFailure(
                        kind="timeout",
                        detail=(
                            f"workload {workload.name!r}: gateway returned HTTP 504 "
                            "upstream request timed out"
                        ),
                    )
                raise RuntimeError(
                    f"workload {workload.name!r} got HTTP {response.status_code}: "
                    f"{body[:500]!r}"
                )
            correlation_id = response.headers.get(_CORRELATION_ID_HEADER)
            for _chunk in response.iter_bytes():
                if client_ttft_ms is None:
                    client_ttft_ms = (time.perf_counter() - start) * 1000
            total_latency_ms = (time.perf_counter() - start) * 1000
    except httpx.TimeoutException as exc:
        # Most specific first: httpx.TimeoutException is itself a
        # httpx.TransportError subclass (mirrors
        # src/proxy/routes.py::_translate_upstream_connection_failure's
        # identical ordering, for the identical reason).
        return _RawFailure(kind="timeout", detail=str(exc))
    except httpx.TransportError as exc:
        return _RawFailure(kind="error", detail=str(exc))

    if not correlation_id:
        raise RuntimeError(
            f"workload {workload.name!r} response carried no "
            f"{_CORRELATION_ID_HEADER!r} header"
        )
    if client_ttft_ms is None:
        # No content byte ever arrived before the stream closed -- every
        # workload in this phase's matrix has non-empty content, so this
        # would indicate a real defect, not a legitimate empty response.
        raise RuntimeError(f"workload {workload.name!r} streamed zero content chunks")
    return _RawSuccess(
        correlation_id=correlation_id,
        request_sent_at_ms=request_sent_at_ms,
        client_ttft_ms=client_ttft_ms,
        client_total_latency_ms=total_latency_ms,
    )


def run_cell(
    base_url: str,
    gateway_log_path: Path,
    workload: LatencyWorkload,
    *,
    concurrency: int,
    total_requests: int,
    warmup_requests: int,
    session_id_prefix: str,
    request_timeout_s: float = DEFAULT_REQUEST_TIMEOUT_S,
) -> CellRawResults:
    """Fire `total_requests` requests at `workload` against the running
    gateway at `base_url`, `concurrency` genuinely in flight at a time,
    then return the combined per-request measurements for every request
    *after* the first `warmup_requests` (discarded, never measured —
    Phase 7 design, "per-cell warm-up") — plus how many of those
    measured requests timed out or failed, which never aborts this
    cell or any later one (Phase 7 design follow-up).

    Each request gets its own fresh `X-Session-Id` — never shared
    across requests in this cell. This harness measures request
    latency, not session-map behaviour under a shared, growing session;
    a shared session would let one repetition's name-allocation/
    collision cost bleed into a later repetition's timing, contaminating
    exactly the "any variance is process noise, not workload noise"
    property the Phase 7 design's noise-minimization section requires.
    """
    with httpx.Client(base_url=base_url, timeout=request_timeout_s) as client:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [
                pool.submit(_send_one, client, workload, f"{session_id_prefix}-{i}")
                for i in range(total_requests)
            ]
            raw_outcomes = [future.result() for future in futures]

    measured_outcomes = raw_outcomes[warmup_requests:]
    successes = [o for o in measured_outcomes if isinstance(o, _RawSuccess)]
    timeout_count = sum(
        1 for o in measured_outcomes if isinstance(o, _RawFailure) and o.kind == "timeout"
    )
    error_count = sum(
        1 for o in measured_outcomes if isinstance(o, _RawFailure) and o.kind == "error"
    )

    time.sleep(_LOG_SETTLE_DELAY_S)
    log_index = index_by_correlation_id(gateway_log_path)

    measurements: list[RequestMeasurement] = []
    for raw in successes:
        record = log_index.get(
            raw.correlation_id, RequestLogRecord(None, None, frozenset())
        )
        ttft_without_window_ms = (
            record.upstream_first_chunk_ms - raw.request_sent_at_ms
            if record.upstream_first_chunk_ms is not None
            else None
        )
        measurements.append(
            RequestMeasurement(
                correlation_id=raw.correlation_id,
                client_ttft_ms=raw.client_ttft_ms,
                client_total_latency_ms=raw.client_total_latency_ms,
                ttft_without_window_ms=ttft_without_window_ms,
                window_tax_ms=window_tax_ms(record),
                window_tax_percent=window_tax_percent(
                    record, request_sent_at_ms=raw.request_sent_at_ms
                ),
                tier_hit_class=classify_tier_hit(record.tiers_hit),
            )
        )
    return CellRawResults(
        measurements=measurements,
        attempted=len(measured_outcomes),
        timeout_count=timeout_count,
        error_count=error_count,
    )
