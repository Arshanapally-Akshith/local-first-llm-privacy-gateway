"""Parses the gateway's captured structured-log file
(`process_harness.ManagedProcess.stderr_log_path` — `logging.StreamHandler()`'s
default stream, where `src/core/logging.py`'s `PiiSafeFormatter` writes,
unchanged) and indexes it by `correlation_id`.

This is what lets a real-subprocess, real-socket harness recover the
two internal timing events (`latency.upstream_first_chunk`,
`latency.window_first_release`, both added to `src/proxy/routes.py` for
this phase) and the per-span tier-hit events (`pipeline.span_sanitized`,
already emitted since Phase 4) that an in-process harness could
otherwise pull straight off an attached `logging.Handler` — see
`latency/__init__.py` for why this harness cannot use that in-process
trick.
"""

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

_UPSTREAM_FIRST_CHUNK_EVENT: str = "latency.upstream_first_chunk"
_WINDOW_FIRST_RELEASE_EVENT: str = "latency.window_first_release"
_SPAN_SANITIZED_EVENT: str = "pipeline.span_sanitized"


@dataclass(frozen=True, slots=True)
class RequestLogRecord:
    """Everything this harness recovers from one request's own log
    lines, keyed by that request's `correlation_id`.
    """

    upstream_first_chunk_ms: float | None
    """Absolute epoch-ms `Clock.now()` reading at the first upstream
    SSE chunk received. `None` for a non-streaming request, or a
    streaming one whose event was never emitted (e.g. a connection
    failure before any chunk arrived)."""

    window_first_release_ms: float | None
    """Absolute epoch-ms `Clock.now()` reading at the first non-empty
    release from the sliding window. `None` under the same conditions
    as `upstream_first_chunk_ms`."""

    tiers_hit: frozenset[int]
    """Which detection tier(s) resolved at least one span in this
    request — empty for a request with no detected entity at all (the
    honest "real traffic is mostly PII-free" case; Phase 7 design)."""


def _iter_gateway_json_lines(path: Path) -> Iterator[dict[str, object]]:
    """Yield every line of `path` that parses as one of the gateway's
    own structured JSON log records (`logger == "gateway"`).

    `uvicorn`'s own interleaved plain-text lines (access logs, "Waiting
    for application startup", huggingface_hub download progress bars,
    ...) are silently skipped, not raised on — they are expected
    non-JSON noise in this file, not malformed data.
    """
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                parsed: object = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and parsed.get("logger") == "gateway":
                yield parsed


def _as_float(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def index_by_correlation_id(path: Path) -> dict[str, RequestLogRecord]:
    """Build one `RequestLogRecord` per distinct `correlation_id` found
    in the gateway's captured log file at `path`.

    A `correlation_id` with no `pipeline.span_sanitized` line at all
    (nothing detected) still gets an entry, with `tiers_hit=frozenset()`
    — the same "finding nothing is normal, not exceptional" contract
    every detector in this codebase already follows.
    """
    upstream_first_chunk: dict[str, float] = {}
    window_first_release: dict[str, float] = {}
    tiers_hit: dict[str, set[int]] = {}
    all_correlation_ids: set[str] = set()

    for record in _iter_gateway_json_lines(path):
        correlation_id = record.get("correlation_id")
        if not isinstance(correlation_id, str):
            continue
        all_correlation_ids.add(correlation_id)
        event = record.get("event")
        if event == _UPSTREAM_FIRST_CHUNK_EVENT:
            timestamp_ms = _as_float(record.get("timestamp_ms"))
            if timestamp_ms is not None:
                upstream_first_chunk[correlation_id] = timestamp_ms
        elif event == _WINDOW_FIRST_RELEASE_EVENT:
            timestamp_ms = _as_float(record.get("timestamp_ms"))
            if timestamp_ms is not None:
                window_first_release[correlation_id] = timestamp_ms
        elif event == _SPAN_SANITIZED_EVENT:
            tier = record.get("tier")
            if isinstance(tier, int):
                tiers_hit.setdefault(correlation_id, set()).add(tier)

    return {
        correlation_id: RequestLogRecord(
            upstream_first_chunk_ms=upstream_first_chunk.get(correlation_id),
            window_first_release_ms=window_first_release.get(correlation_id),
            tiers_hit=frozenset(tiers_hit.get(correlation_id, set())),
        )
        for correlation_id in all_correlation_ids
    }


def find_latency_ms(path: Path, *, event: str, correlation_id: str) -> float | None:
    """Return the `latency_ms` field of the first log line in `path`
    matching `event`/`correlation_id`, or `None` if no such line exists.

    Used by the cold-start section of `run.py` to read back
    `app/main.py`'s own `startup.tier2_model_warmed` event — Phase 4's
    own instrumentation, already carrying the exact cold-start duration
    this harness needs (`event="startup.tier2_model_warmed",
    correlation_id="startup"`), not something Phase 7 adds.
    """
    for record in _iter_gateway_json_lines(path):
        if record.get("event") == event and record.get("correlation_id") == correlation_id:
            return _as_float(record.get("latency_ms"))
    return None


def classify_tier_hit(tiers_hit: frozenset[int]) -> str:
    """Categorical tier-hit classification for one request — reported
    as a distribution across a cell's requests, never blended into a
    latency percentile (Phase 7 design: "never blended into the
    latency percentiles").
    """
    if tiers_hit == frozenset({1}):
        return "tier1_only"
    if tiers_hit == frozenset({2}):
        return "tier2_only"
    if tiers_hit == frozenset({1, 2}):
        return "both"
    return "neither"


def window_tax_ms(record: RequestLogRecord) -> float | None:
    """`window_first_release_ms - upstream_first_chunk_ms` — how much
    additional time the sliding window (and the detection/rehydration
    work it gates) added on top of the upstream's own raw
    responsiveness. Needs no external request-start reference: both
    timestamps come from the same process's `Clock`, so their
    difference is well-defined regardless of when the request was
    actually sent.

    `None` if either half is missing (non-streaming request, or a
    streaming one that never got far enough to emit both events).
    """
    if record.upstream_first_chunk_ms is None or record.window_first_release_ms is None:
        return None
    return record.window_first_release_ms - record.upstream_first_chunk_ms


def window_tax_percent(record: RequestLogRecord, *, request_sent_at_ms: float) -> float | None:
    """`(TTFT_with - TTFT_without) / TTFT_without * 100`, both TTFTs
    measured from `request_sent_at_ms` (Phase 7 design refinement).

    Unlike `window_tax_ms`, this *does* need an external time
    reference: the percentage's denominator is `TTFT_without`
    (elapsed time from request-send to the upstream's first byte), not
    the raw tax itself. `request_sent_at_ms` must be the harness's own
    client-side epoch-ms timestamp, taken immediately before sending
    this exact request, on the same machine's clock as the gateway's
    `Clock` (both processes run on localhost — no cross-host clock-skew
    concern).
    """
    if record.upstream_first_chunk_ms is None or record.window_first_release_ms is None:
        return None
    ttft_without = record.upstream_first_chunk_ms - request_sent_at_ms
    if ttft_without <= 0:
        # A non-positive denominator here means the client-side send
        # timestamp and the gateway-side receive timestamp disagree
        # about ordering (clock jitter at microsecond scale, not a
        # real negative latency) -- reported as unmeasurable for this
        # request rather than a misleading/undefined percentage.
        return None
    ttft_with = record.window_first_release_ms - request_sent_at_ms
    return (ttft_with - ttft_without) / ttft_without * 100
