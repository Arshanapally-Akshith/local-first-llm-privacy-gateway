"""Unit tests for `latency/runner/run.py::_build_cell_report` and
`render_markdown` — specifically the Phase 7 timeout-handling fix: a
cell where every request timed out must produce a report with `None`
latency stats (not crash `summarize()` on an empty list), and
`render_markdown` must render that cell as "n/a", not raise.
"""

from latency.runner.measure import CellRawResults, RequestMeasurement
from latency.runner.run import CONCURRENCY_LEVELS, LatencyReport, _build_cell_report, render_markdown
from latency.runner.stats import summarize
from latency.workloads.definitions import BASELINE_CLEAN, WORKLOADS


def _measurement(correlation_id: str, ttft_ms: float, total_ms: float) -> RequestMeasurement:
    return RequestMeasurement(
        correlation_id=correlation_id,
        client_ttft_ms=ttft_ms,
        client_total_latency_ms=total_ms,
        ttft_without_window_ms=ttft_ms - 5.0,
        window_tax_ms=5.0,
        window_tax_percent=10.0,
        tier_hit_class="neither",
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
