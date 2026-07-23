"""Unit tests for `latency/runner/log_capture.py` against a synthetic
log file — no real subprocess needed, since this module only ever
parses whatever text ends up at a given path.
"""

import json
from pathlib import Path

from latency.runner.log_capture import (
    RequestLogRecord,
    classify_tier_hit,
    find_latency_ms,
    index_by_correlation_id,
    window_tax_ms,
    window_tax_percent,
)


def _json_line(**fields: object) -> str:
    return json.dumps({"logger": "gateway", **fields})


def test_index_by_correlation_id_extracts_both_timing_events(tmp_path: Path) -> None:
    log_path = tmp_path / "gateway_stderr.log"
    log_path.write_text(
        "\n".join(
            [
                _json_line(
                    correlation_id="req-1",
                    event="latency.upstream_first_chunk",
                    timestamp_ms=1000.0,
                ),
                _json_line(
                    correlation_id="req-1",
                    event="latency.window_first_release",
                    timestamp_ms=1050.0,
                ),
            ]
        ),
        encoding="utf-8",
    )

    index = index_by_correlation_id(log_path)

    assert index["req-1"].upstream_first_chunk_ms == 1000.0
    assert index["req-1"].window_first_release_ms == 1050.0


def test_index_by_correlation_id_skips_non_json_and_non_gateway_lines(tmp_path: Path) -> None:
    """uvicorn's own interleaved plain-text lines (access logs, startup
    banners) and any JSON line from a different logger must be skipped,
    not raised on."""
    log_path = tmp_path / "gateway_stderr.log"
    log_path.write_text(
        "\n".join(
            [
                "INFO:     Uvicorn running on http://127.0.0.1:8180",
                json.dumps({"logger": "mock_upstream", "event": "something"}),
                _json_line(
                    correlation_id="req-1",
                    event="latency.upstream_first_chunk",
                    timestamp_ms=500.0,
                ),
                "",
                "not json at all {{{",
            ]
        ),
        encoding="utf-8",
    )

    index = index_by_correlation_id(log_path)

    assert set(index) == {"req-1"}
    assert index["req-1"].upstream_first_chunk_ms == 500.0


def test_index_by_correlation_id_collects_tiers_hit_across_multiple_spans(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "gateway_stderr.log"
    log_path.write_text(
        "\n".join(
            [
                _json_line(correlation_id="req-1", event="pipeline.span_sanitized", tier=1),
                _json_line(correlation_id="req-1", event="pipeline.span_sanitized", tier=2),
                _json_line(correlation_id="req-2", event="pipeline.span_sanitized", tier=1),
            ]
        ),
        encoding="utf-8",
    )

    index = index_by_correlation_id(log_path)

    assert index["req-1"].tiers_hit == frozenset({1, 2})
    assert index["req-2"].tiers_hit == frozenset({1})


def test_index_by_correlation_id_with_no_spans_yields_empty_tiers_hit(tmp_path: Path) -> None:
    log_path = tmp_path / "gateway_stderr.log"
    log_path.write_text(
        _json_line(correlation_id="req-1", event="latency.upstream_first_chunk", timestamp_ms=1.0),
        encoding="utf-8",
    )

    index = index_by_correlation_id(log_path)

    assert index["req-1"].tiers_hit == frozenset()


def test_find_latency_ms_returns_matching_event(tmp_path: Path) -> None:
    log_path = tmp_path / "gateway_stderr.log"
    log_path.write_text(
        "\n".join(
            [
                _json_line(correlation_id="other", event="startup.tier2_model_warmed", latency_ms=1.0),
                _json_line(
                    correlation_id="startup", event="startup.tier2_model_warmed", latency_ms=23873.7
                ),
            ]
        ),
        encoding="utf-8",
    )

    result = find_latency_ms(
        log_path, event="startup.tier2_model_warmed", correlation_id="startup"
    )

    assert result == 23873.7


def test_find_latency_ms_returns_none_when_absent(tmp_path: Path) -> None:
    log_path = tmp_path / "gateway_stderr.log"
    log_path.write_text("", encoding="utf-8")

    assert find_latency_ms(log_path, event="anything", correlation_id="startup") is None


def test_classify_tier_hit() -> None:
    assert classify_tier_hit(frozenset()) == "neither"
    assert classify_tier_hit(frozenset({1})) == "tier1_only"
    assert classify_tier_hit(frozenset({2})) == "tier2_only"
    assert classify_tier_hit(frozenset({1, 2})) == "both"


def test_window_tax_ms_is_the_difference_regardless_of_absolute_scale() -> None:
    record = RequestLogRecord(
        upstream_first_chunk_ms=1_000_000.0,
        window_first_release_ms=1_000_042.0,
        tiers_hit=frozenset(),
    )

    assert window_tax_ms(record) == 42.0


def test_window_tax_ms_is_none_when_either_timestamp_is_missing() -> None:
    assert window_tax_ms(RequestLogRecord(None, 100.0, frozenset())) is None
    assert window_tax_ms(RequestLogRecord(100.0, None, frozenset())) is None


def test_window_tax_percent_matches_the_documented_formula() -> None:
    # request sent at t=0; upstream first byte at t=100ms (TTFT_without);
    # window releases at t=150ms (TTFT_with) -> 50% tax.
    record = RequestLogRecord(
        upstream_first_chunk_ms=100.0, window_first_release_ms=150.0, tiers_hit=frozenset()
    )

    result = window_tax_percent(record, request_sent_at_ms=0.0)

    assert result == 50.0


def test_window_tax_percent_is_none_when_denominator_is_non_positive() -> None:
    """A non-positive TTFT_without would mean the upstream's first byte
    was logged at or before the client's own send timestamp -- clock
    jitter, not a real latency -- reported as unmeasurable rather than
    an undefined or misleading percentage."""
    record = RequestLogRecord(
        upstream_first_chunk_ms=100.0, window_first_release_ms=150.0, tiers_hit=frozenset()
    )

    assert window_tax_percent(record, request_sent_at_ms=100.0) is None
    assert window_tax_percent(record, request_sent_at_ms=200.0) is None
