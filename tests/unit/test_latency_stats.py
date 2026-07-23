"""Unit tests for `latency/runner/stats.py::summarize()` — the one
statistics implementation this package's every metric reuses (Phase 7
design: "no duplicated logic")."""

import pytest

from latency.runner.stats import summarize


def test_summarize_computes_mean_median_min_max() -> None:
    result = summarize([10.0, 20.0, 30.0, 40.0, 50.0])

    assert result["n"] == 5
    assert result["mean"] == 30.0
    assert result["median"] == 30.0
    assert result["min"] == 10.0
    assert result["max"] == 50.0


def test_summarize_p95_and_p99_use_linear_interpolation() -> None:
    """Fixed method, stated in the module docstring: linear
    interpolation between the two nearest ranks, matching NumPy's
    default `numpy.percentile`. For 0..100 (101 values), p95 lands
    exactly on rank 95 with no interpolation needed, a convenient
    sanity check of the fixed method."""
    result = summarize([float(i) for i in range(101)])

    assert result["p95"] == 95.0
    assert result["p99"] == 99.0


def test_summarize_stdev_and_cv() -> None:
    result = summarize([10.0, 10.0, 10.0])

    assert result["stdev"] == 0.0
    assert result["cv"] == 0.0


def test_summarize_cv_is_stdev_over_mean() -> None:
    result = summarize([10.0, 20.0])

    assert result["mean"] == 15.0
    assert result["cv"] == pytest.approx(result["stdev"] / result["mean"])


def test_summarize_single_sample_has_zero_stdev_and_cv_and_all_percentiles_equal_the_value() -> (
    None
):
    result = summarize([42.0])

    assert result["n"] == 1
    assert result["mean"] == 42.0
    assert result["median"] == 42.0
    assert result["p95"] == 42.0
    assert result["p99"] == 42.0
    assert result["stdev"] == 0.0
    assert result["cv"] == 0.0
    assert result["min"] == 42.0
    assert result["max"] == 42.0


def test_summarize_empty_sequence_raises_value_error() -> None:
    """Every caller in this package has a fixed, known repetition count
    before calling `summarize()` — an empty sample here is a harness
    bug, not a data condition to silently report as zeros."""
    with pytest.raises(ValueError, match="at least one sample"):
        summarize([])


def test_summarize_does_not_mutate_the_input_sequence() -> None:
    values = [30.0, 10.0, 20.0]

    summarize(values)

    assert values == [30.0, 10.0, 20.0]
