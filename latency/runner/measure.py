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
"""

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

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

_REQUEST_TIMEOUT_S: float = 60.0
_LOG_SETTLE_DELAY_S: float = 0.1
"""A short, explicitly-not-a-measurement settle delay before reading
back the gateway's captured log file at the end of a batch:
`logging.StreamHandler.emit()` flushes after every write, so this is
pure insurance against OS-level file-visibility latency between the
child process's write and this process's read of the same file --
never counted as part of any reported metric."""


@dataclass(frozen=True, slots=True)
class RequestMeasurement:
    """One request's fully combined measurement — client-observed
    timing plus the gateway's own internal log-derived timing, joined
    by `correlation_id`.
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
class _RawResult:
    correlation_id: str
    request_sent_at_ms: float
    client_ttft_ms: float
    client_total_latency_ms: float


def _send_one(client: httpx.Client, workload: LatencyWorkload, session_id: str) -> _RawResult:
    """Send one streaming request over a real socket and time it from
    the client's own perspective.

    Raises:
        RuntimeError: a non-200 response, or a response missing the
            `X-Correlation-Id` header — both are harness/gateway
            defects for these fixed, known-good workloads, never a
            latency sample worth silently recording as zero.
    """
    request_sent_at_ms = time.time() * 1000
    start = time.perf_counter()
    client_ttft_ms: float | None = None
    with client.stream(
        "POST",
        _CHAT_COMPLETIONS_PATH,
        json=workload.request_body,
        headers={_SESSION_ID_HEADER: session_id},
    ) as response:
        if response.status_code != 200:
            body = response.read()
            raise RuntimeError(
                f"workload {workload.name!r} got HTTP {response.status_code}: "
                f"{body[:500]!r}"
            )
        correlation_id = response.headers.get(_CORRELATION_ID_HEADER)
        for _chunk in response.iter_bytes():
            if client_ttft_ms is None:
                client_ttft_ms = (time.perf_counter() - start) * 1000
        total_latency_ms = (time.perf_counter() - start) * 1000

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
    return _RawResult(
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
) -> list[RequestMeasurement]:
    """Fire `total_requests` requests at `workload` against the running
    gateway at `base_url`, `concurrency` genuinely in flight at a time,
    then return the combined per-request measurements for every request
    *after* the first `warmup_requests` (discarded, never measured —
    Phase 7 design, "per-cell warm-up").

    Each request gets its own fresh `X-Session-Id` — never shared
    across requests in this cell. This harness measures request
    latency, not session-map behaviour under a shared, growing session;
    a shared session would let one repetition's name-allocation/
    collision cost bleed into a later repetition's timing, contaminating
    exactly the "any variance is process noise, not workload noise"
    property the Phase 7 design's noise-minimization section requires.
    """
    with httpx.Client(base_url=base_url, timeout=_REQUEST_TIMEOUT_S) as client:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [
                pool.submit(_send_one, client, workload, f"{session_id_prefix}-{i}")
                for i in range(total_requests)
            ]
            raw_results = [future.result() for future in futures]

    time.sleep(_LOG_SETTLE_DELAY_S)
    log_index = index_by_correlation_id(gateway_log_path)

    measurements: list[RequestMeasurement] = []
    for raw in raw_results[warmup_requests:]:
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
    return measurements
