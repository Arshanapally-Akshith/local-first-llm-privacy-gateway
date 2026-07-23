"""Unit tests for `latency/runner/run.py::_build_cell_report` and
`render_markdown` — the Phase 7 timeout-handling fix (a cell where
every request timed out must produce a report with `None` latency
stats, not crash `summarize()` on an empty list, and `render_markdown`
must render that cell as "n/a", not raise) and the Phase 7 DoD's
"Per-tier p50/p95/p99" fix (TTFT grouped by `tier_hit_class`, only
populated classes present, never a `None` placeholder for an empty one).
"""

from latency.runner.measure import CellRawResults, RequestMeasurement
from latency.runner.run import CONCURRENCY_LEVELS, LatencyReport, _build_cell_report, render_markdown
from latency.runner.stats import summarize
from latency.workloads.definitions import BASELINE_CLEAN, WORKLOADS


def _measurement(
    correlation_id: str,
    ttft_ms: float,
    total_ms: float,
    tier_hit_class: str = "neither",
) -> RequestMeasurement:
    return RequestMeasurement(
        correlation_id=correlation_id,
        client_ttft_ms=ttft_ms,
        client_total_latency_ms=total_ms,
        ttft_without_window_ms=ttft_ms - 5.0,
        window_tax_ms=5.0,
        window_tax_percent=10.0,
        tier_hit_class=tier_hit_class,
    )


def test_build_cell_report_with_successes_populates_all_stats() -> None:
    raw = CellRawResults(
        measurements=[
            _measurement("corr-0", 100.0, 200.0),
            _measurement("corr-1", 110.0, 210.0),
        ],
        attempted=2,
        timeout_count=0,
        error_count=0,
    )

    report = _build_cell_report(BASELINE_CLEAN, 4, raw)

    assert report["n"] == 2
    assert report["attempted"] == 2
    assert report["timeout_count"] == 0
    assert report["error_count"] == 0
    assert report["ttft_with_window_ms"] is not None
    assert report["ttft_with_window_ms"]["mean"] == 105.0
    assert report["total_latency_ms"] is not None
    assert report["window_tax_ms"] is not None
    assert report["window_tax_percent"] is not None


def test_build_cell_report_with_all_requests_timed_out_reports_none_stats_not_a_crash() -> None:
    raw = CellRawResults(measurements=[], attempted=5, timeout_count=5, error_count=0)

    report = _build_cell_report(BASELINE_CLEAN, 16, raw)

    assert report["n"] == 0
    assert report["attempted"] == 5
    assert report["timeout_count"] == 5
    assert report["ttft_with_window_ms"] is None
    assert report["ttft_without_window_ms"] is None
    assert report["total_latency_ms"] is None
    assert report["window_tax_ms"] is None
    assert report["window_tax_percent"] is None
    assert report["tier_hit"] == {}
    assert report["per_tier_ttft_with_window_ms"] == {}


def test_build_cell_report_with_mixed_success_and_failure() -> None:
    raw = CellRawResults(
        measurements=[_measurement("corr-0", 100.0, 200.0)],
        attempted=3,
        timeout_count=1,
        error_count=1,
    )

    report = _build_cell_report(BASELINE_CLEAN, 8, raw)

    assert report["n"] == 1
    assert report["attempted"] == 3
    assert report["timeout_count"] == 1
    assert report["error_count"] == 1
    assert report["ttft_with_window_ms"] is not None


def test_per_tier_ttft_groups_by_tier_hit_class_and_omits_unpopulated_classes() -> None:
    """BUILD.md Phase 7 DoD: "Per-tier p50/p95/p99" -- TTFT grouped by
    which tier resolved the request, computed independently per class,
    with a class absent (never null/zero) when this cell had no
    completed request of that class."""
    raw = CellRawResults(
        measurements=[
            _measurement("corr-0", 100.0, 200.0, tier_hit_class="tier1_only"),
            _measurement("corr-1", 120.0, 220.0, tier_hit_class="tier1_only"),
            _measurement("corr-2", 500.0, 600.0, tier_hit_class="tier2_only"),
        ],
        attempted=3,
        timeout_count=0,
        error_count=0,
    )

    report = _build_cell_report(BASELINE_CLEAN, 4, raw)

    per_tier = report["per_tier_ttft_with_window_ms"]
    assert set(per_tier) == {"tier1_only", "tier2_only"}
    assert per_tier["tier1_only"]["mean"] == 110.0
    assert per_tier["tier1_only"]["n"] == 2
    assert per_tier["tier2_only"]["mean"] == 500.0
    assert per_tier["tier2_only"]["n"] == 1
    # "both" and "neither" had zero completed requests in this cell --
    # absent, not a None/zero placeholder.
    assert "both" not in per_tier
    assert "neither" not in per_tier


def test_per_tier_ttft_with_a_single_populated_class_omits_the_other_three() -> None:
    """The common case for most of this phase's 8 workloads, which were
    deliberately built to isolate one tier's cost -- e.g. tier1_only's
    own cell should show exactly one populated class, not four with
    three empty placeholders."""
    raw = CellRawResults(
        measurements=[_measurement("corr-0", 100.0, 200.0, tier_hit_class="tier1_only")],
        attempted=1,
        timeout_count=0,
        error_count=0,
    )

    report = _build_cell_report(BASELINE_CLEAN, 1, raw)

    assert set(report["per_tier_ttft_with_window_ms"]) == {"tier1_only"}


def test_per_tier_ttft_does_not_affect_the_aggregate_ttft_stat() -> None:
    """Existing aggregate statistics must be unchanged by this
    addition -- the aggregate is over ALL completed requests regardless
    of tier, exactly as before."""
    raw = CellRawResults(
        measurements=[
            _measurement("corr-0", 100.0, 200.0, tier_hit_class="tier1_only"),
            _measurement("corr-1", 500.0, 600.0, tier_hit_class="tier2_only"),
        ],
        attempted=2,
        timeout_count=0,
        error_count=0,
    )

    report = _build_cell_report(BASELINE_CLEAN, 4, raw)

    assert report["ttft_with_window_ms"] is not None
    assert report["ttft_with_window_ms"]["mean"] == 300.0
    assert report["ttft_with_window_ms"]["n"] == 2


def test_render_markdown_renders_per_tier_breakdown_only_for_populated_classes() -> None:
    mixed = _build_cell_report(
        BASELINE_CLEAN,
        4,
        CellRawResults(
            measurements=[
                _measurement("corr-0", 100.0, 200.0, tier_hit_class="tier1_only"),
                _measurement("corr-1", 500.0, 600.0, tier_hit_class="tier2_only"),
            ],
            attempted=2,
            timeout_count=0,
            error_count=0,
        ),
    )
    report = LatencyReport(
        commit="deadbeef",
        concurrency_levels=list(CONCURRENCY_LEVELS),
        steady_state_repetitions=200,
        request_timeout_s=120.0,
        cold_start_repetitions=10,
        cold_start_ms=summarize([1000.0, 1100.0]),
        cells=[mixed],
        caveat="test caveat",
    )

    rendered = render_markdown(report)

    assert "| 4 | tier1_only |" in rendered
    assert "| 4 | tier2_only |" in rendered
    # The per-tier table's row format is "| {concurrency} | {klass} | ..." --
    # a row for an unpopulated class would contain one of these exact
    # substrings. (BASELINE_CLEAN.description itself contains the plain
    # English word "both", so a whole-document substring check would be
    # a false positive -- this checks the table row shape specifically.)
    assert "| both |" not in rendered
    assert "| neither |" not in rendered


def test_render_markdown_handles_a_fully_failed_cell_without_raising() -> None:
    all_failed = _build_cell_report(
        BASELINE_CLEAN, 16, CellRawResults(measurements=[], attempted=10, timeout_count=10, error_count=0)
    )
    succeeded = _build_cell_report(
        BASELINE_CLEAN,
        1,
        CellRawResults(measurements=[_measurement("corr-0", 100.0, 200.0)], attempted=1, timeout_count=0, error_count=0),
    )
    report = LatencyReport(
        commit="deadbeef",
        concurrency_levels=list(CONCURRENCY_LEVELS),
        steady_state_repetitions=200,
        request_timeout_s=120.0,
        cold_start_repetitions=10,
        cold_start_ms=summarize([1000.0, 1100.0]),
        cells=[all_failed, succeeded],
        caveat="test caveat",
    )

    rendered = render_markdown(report)

    assert "n/a" in rendered
    assert BASELINE_CLEAN.name in rendered
    for workload in WORKLOADS:
        assert workload.name in rendered
