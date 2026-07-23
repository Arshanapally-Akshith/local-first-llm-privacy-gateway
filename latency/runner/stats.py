"""Statistics for the Phase 7 latency harness.

One function (`summarize()`), reused for every metric this harness
reports — TTFT with the window, TTFT without the window, total
latency, `window_tax_ms`, and `window_tax_percent`, and the cold-start
distribution. CLAUDE.md: "No duplicated logic" — a second, slightly
different percentile implementation for even one of these metrics would
make two numbers in the same report silently incomparable.

Percentile method: linear interpolation between the two nearest ranks
(the method NumPy's default `numpy.percentile` and Excel's
PERCENTILE.INC use) — fixed once, here, and applied identically to
every metric this package reports, mirroring `docs/DECISIONS.md`'s
span-matching-criterion discipline for the Phase 5 benchmark ("pick
one, justify it, apply it identically to all arms").
"""

import statistics
from collections.abc import Sequence
from typing import TypedDict


class StatsSummary(TypedDict):
    n: int
    mean: float
    median: float
    p95: float
    p99: float
    stdev: float
    cv: float
    """Coefficient of variation, stdev / mean — 0.0 when mean is 0.0
    (an all-zero sample), never a division error. Reported alongside
    mean/stdev on every metric block (Phase 7 design refinement)."""
    min: float
    max: float


def _percentile(sorted_values: Sequence[float], fraction: float) -> float:
    """Linear-interpolation percentile of an already-sorted sequence.

    `fraction` is in `[0, 1]` (`0.95` for p95, `0.99` for p99).
    Precondition: `sorted_values` is non-empty and sorted ascending —
    the only caller, `summarize()`, always passes its own already-
    validated, already-sorted copy.
    """
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = fraction * (len(sorted_values) - 1)
    lower_index = int(rank)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    fractional = rank - lower_index
    return (
        sorted_values[lower_index]
        + (sorted_values[upper_index] - sorted_values[lower_index]) * fractional
    )


def summarize(values: Sequence[float]) -> StatsSummary:
    """Return the fixed statistics block for one metric's samples.

    Used identically for every cell's TTFT/total-latency/window-tax
    numbers and for the cold-start distribution — a small sample there
    (n=10, Phase 7 design refinement) makes p95/p99 indicative rather
    than statistically robust, which the harness's own report caveat
    states explicitly rather than hiding behind a second, smaller
    statistics shape that only reports min/median/max.

    Raises:
        ValueError: `values` is empty. Every caller in this package
            has a fixed, known repetition count before it ever calls
            this — an empty sample here is a harness bug (e.g. a cell
            that ran zero repetitions), not a data condition worth
            reporting as zeros.
    """
    if not values:
        raise ValueError("summarize() requires at least one sample")
    sorted_values = sorted(values)
    mean = statistics.mean(sorted_values)
    stdev = statistics.stdev(sorted_values) if len(sorted_values) > 1 else 0.0
    return StatsSummary(
        n=len(sorted_values),
        mean=mean,
        median=statistics.median(sorted_values),
        p95=_percentile(sorted_values, 0.95),
        p99=_percentile(sorted_values, 0.99),
        stdev=stdev,
        cv=(stdev / mean) if mean != 0 else 0.0,
        min=sorted_values[0],
        max=sorted_values[-1],
    )
