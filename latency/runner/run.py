"""The Phase 7 latency harness entrypoint.

Run with:
    python -m latency.runner.run [--repetitions N] [--request-timeout SECONDS] [--pilot-only]

Spawns the real gateway (`app.main:app`) and the real mock upstream
(`src.mock_upstream.main:app`) as `uvicorn` subprocesses over real
sockets (`process_harness.py` — the deliberate departure from the
in-process pattern the other three runners share; see
`latency/__init__.py`), measures cold start as its own, separate
10-fresh-process section, then runs the fixed 8-workload x
5-concurrency-level matrix (40 cells) at `--repetitions` per cell
(default 200) with the first 10 requests of every cell discarded as
warm-up. Writes `latency/results/latest.json` (canonical,
commit-stamped) and `latest.md` (a pure rendering of the same data) —
mirroring `benchmarks/runner/run.py`, `adversarial/runner/run.py`, and
`rehydration_fidelity/runner/run.py`'s identical `build_report()`/
`main()` split.

`--pilot-only` runs the same 40-cell matrix at a much smaller n (20 per
cell), prints each cell's mean latency, and projects the full run's
wall-clock time by scaling the pilot's own *measured* elapsed time —
never a formula-based guess. Writes no artifact. This is the Phase 7
design's "pilot-then-commit" discipline: run this once before a long
committed run to decide whether `--repetitions` needs adjusting for
the machine actually running it, rather than the harness silently
guessing (or silently self-adjusting) a repetition count on its own.

A per-request timeout is a measured, reported *outcome* of a cell, not
a fatal error that aborts the whole run — a real pilot run hit the
previous fixed 60s timeout on `multiturn_5` at concurrency=8 and took
the entire run down with it. See `latency/runner/measure.py`'s module
docstring and `docs/DECISIONS.md` (2026-07-23, "Phase 7 Task 2
follow-up") for the investigation and the fix: `--request-timeout`
(default `measure.DEFAULT_REQUEST_TIMEOUT_S`) is now configurable, and
every `CellReport` below carries its own `timeout_count`/`error_count`
alongside `n` (successes) — excluded from every latency percentile,
never silently dropped.

Like the other three runners, this module does not touch a top-level
`README.md` — Phase 8 owns assembling that.
"""

import argparse
import json
import logging
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Final, TypedDict

from latency.runner.log_capture import find_latency_ms
from latency.runner.measure import DEFAULT_REQUEST_TIMEOUT_S, CellRawResults, run_cell
from latency.runner.process_harness import running_gateway_alone, running_gateway_and_mock
from latency.runner.stats import StatsSummary, summarize
from latency.workloads.definitions import WORKLOADS
from latency.workloads.workload_types import LatencyWorkload

_logger = logging.getLogger("latency.runner")
_logger.setLevel(logging.INFO)
_logger.addHandler(logging.StreamHandler())

_RESULTS_DIR: Final[Path] = Path(__file__).resolve().parent.parent / "results"
_JSON_PATH: Final[Path] = _RESULTS_DIR / "latest.json"
_MARKDOWN_PATH: Final[Path] = _RESULTS_DIR / "latest.md"


def _fresh_process_log_dir() -> Path:
    """A fresh, process-owned temp directory for one invocation's raw
    uvicorn stdout/stderr capture — never under the repo tree, so there
    is nothing here to `.gitignore` and nothing to accidentally commit.
    Not cleaned up automatically on exit: left on disk for a human to
    inspect after a run, the same tradeoff `tempfile.mkdtemp()` (as
    opposed to `TemporaryDirectory`) always makes."""
    return Path(tempfile.mkdtemp(prefix="latency_harness_"))


CONCURRENCY_LEVELS: Final[tuple[int, ...]] = (1, 2, 4, 8, 16)
PILOT_REPETITIONS: Final[int] = 20
WARMUP_REPETITIONS: Final[int] = 10
DEFAULT_STEADY_STATE_REPETITIONS: Final[int] = 200
COLD_START_REPETITIONS: Final[int] = 10

_CAVEAT: Final[str] = (
    "measured-on-benchmark, not real traffic -- tier-hit rate is a property "
    "of this harness's own fixed workload matrix's PII density, not of real "
    "traffic (ARCHITECTURE.md, 'The cascade'). Every row below states its "
    "own concurrency level; this artifact never reports a p99 without one, "
    "per BUILD.md Phase 7. Cold start (n=10, a fresh process each time) is "
    "reported separately and is never folded into any steady-state row. A "
    "request that timed out (or otherwise failed to complete) within this "
    "run's --request-timeout ceiling is excluded from every latency "
    "percentile below and counted instead in that cell's own "
    "timeout_count/error_count -- a cell with a nonzero count completed "
    "fewer than n requests and that is itself part of the finding, not a "
    "gap silently papered over."
)


class CellReport(TypedDict):
    workload: str
    concurrency: int
    n: int
    """Successful requests actually summarized below -- may be less
    than `attempted` when `timeout_count`/`error_count` is nonzero."""
    attempted: int
    """Post-warmup requests this cell actually tried: `n` +
    `timeout_count` + `error_count`."""
    timeout_count: int
    error_count: int
    warmup_discarded: int
    ttft_with_window_ms: StatsSummary | None
    ttft_without_window_ms: StatsSummary | None
    total_latency_ms: StatsSummary | None
    window_tax_ms: StatsSummary | None
    window_tax_percent: StatsSummary | None
    tier_hit: dict[str, float]


class LatencyReport(TypedDict):
    commit: str
    concurrency_levels: list[int]
    steady_state_repetitions: int
    request_timeout_s: float
    cold_start_repetitions: int
    cold_start_ms: StatsSummary
    cells: list[CellReport]
    caveat: str


def _current_commit_hash() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).resolve().parent,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return completed.stdout.strip()


def _tier_hit_distribution(raw: CellRawResults) -> dict[str, float]:
    if not raw.measurements:
        return {}
    counts: dict[str, int] = {}
    for measurement in raw.measurements:
        counts[measurement.tier_hit_class] = counts.get(measurement.tier_hit_class, 0) + 1
    total = len(raw.measurements)
    return {klass: count / total for klass, count in sorted(counts.items())}


def _build_cell_report(
    workload: LatencyWorkload, concurrency: int, raw: CellRawResults
) -> CellReport:
    """Build one cell's report from its raw results.

    Every stats field is `None` when its underlying sample is empty —
    which for `ttft_with_window_ms`/`ttft_without_window_ms`/
    `total_latency_ms` only happens if *every* request in this cell
    timed out or failed (`n == 0`); `summarize()` itself still raises
    on an empty list, so this function guards the call rather than
    letting a fully-failed cell crash the whole report.
    """
    measurements = raw.measurements
    window_taxes = [m.window_tax_ms for m in measurements if m.window_tax_ms is not None]
    window_tax_percents = [
        m.window_tax_percent for m in measurements if m.window_tax_percent is not None
    ]
    ttft_without_window_samples = [
        m.ttft_without_window_ms for m in measurements if m.ttft_without_window_ms is not None
    ]
    return CellReport(
        workload=workload.name,
        concurrency=concurrency,
        n=len(measurements),
        attempted=raw.attempted,
        timeout_count=raw.timeout_count,
        error_count=raw.error_count,
        warmup_discarded=WARMUP_REPETITIONS,
        ttft_with_window_ms=(
            summarize([m.client_ttft_ms for m in measurements]) if measurements else None
        ),
        ttft_without_window_ms=(
            summarize(ttft_without_window_samples) if ttft_without_window_samples else None
        ),
        total_latency_ms=(
            summarize([m.client_total_latency_ms for m in measurements]) if measurements else None
        ),
        window_tax_ms=summarize(window_taxes) if window_taxes else None,
        window_tax_percent=summarize(window_tax_percents) if window_tax_percents else None,
        tier_hit=_tier_hit_distribution(raw),
    )


def _run_matrix(
    gateway_base_url: str,
    gateway_log_path: Path,
    repetitions: int,
    request_timeout_s: float,
) -> list[CellReport]:
    """Run every workload at every concurrency level, `repetitions`
    measured requests per cell (plus `WARMUP_REPETITIONS` discarded
    ahead of them) — 8 x 5 = 40 cells, in the same fixed order every
    time (`WORKLOADS` x `CONCURRENCY_LEVELS`, both fixed tuples).

    A cell with any timeouts/errors is logged loudly but never stops
    this loop — the next cell always runs regardless of how the
    previous one went (Phase 7 design follow-up: "continue executing
    the remaining benchmark cells after a timeout").
    """
    cells: list[CellReport] = []
    for workload in WORKLOADS:
        for concurrency in CONCURRENCY_LEVELS:
            _logger.info(
                "running workload=%s concurrency=%d n=%d (+%d warmup, timeout=%.0fs)",
                workload.name,
                concurrency,
                repetitions,
                WARMUP_REPETITIONS,
                request_timeout_s,
            )
            raw = run_cell(
                gateway_base_url,
                gateway_log_path,
                workload,
                concurrency=concurrency,
                total_requests=repetitions + WARMUP_REPETITIONS,
                warmup_requests=WARMUP_REPETITIONS,
                session_id_prefix=f"latency-{workload.name}-c{concurrency}",
                request_timeout_s=request_timeout_s,
            )
            if raw.timeout_count or raw.error_count:
                _logger.warning(
                    "workload=%s concurrency=%d: %d succeeded, %d timed out, %d errored "
                    "(of %d attempted)",
                    workload.name,
                    concurrency,
                    len(raw.measurements),
                    raw.timeout_count,
                    raw.error_count,
                    raw.attempted,
                )
            cells.append(_build_cell_report(workload, concurrency, raw))
    return cells


def _measure_cold_start(log_root: Path) -> StatsSummary:
    """Spawn `COLD_START_REPETITIONS` genuinely fresh gateway processes,
    one at a time, and read back each one's own
    `startup.tier2_model_warmed` `latency_ms` — Phase 4's own
    instrumentation, already exactly the number this section needs.

    A fresh *process* per sample, not a fresh in-process model
    reload: only a real process boot pays the full cold-start cost
    (import time, model load, first inference) BUILD.md's Phase 7
    names ("First inference is seconds... do not let it hide inside
    p50 later").
    """
    samples: list[float] = []
    for i in range(COLD_START_REPETITIONS):
        with running_gateway_alone(log_root / f"cold_start_{i}") as gateway:
            latency_ms = find_latency_ms(
                gateway.stderr_log_path,
                event="startup.tier2_model_warmed",
                correlation_id="startup",
            )
        if latency_ms is None:
            raise RuntimeError(
                f"cold-start run {i}: no startup.tier2_model_warmed event found in "
                f"{gateway.stderr_log_path} -- NER_WARMUP must be enabled for this "
                "measurement to mean anything (process_harness._base_env() sets it)."
            )
        _logger.info("cold_start run=%d latency_ms=%.1f", i, latency_ms)
        samples.append(latency_ms)
    return summarize(samples)


def build_report(
    *,
    repetitions: int = DEFAULT_STEADY_STATE_REPETITIONS,
    request_timeout_s: float = DEFAULT_REQUEST_TIMEOUT_S,
) -> LatencyReport:
    """Run the full cold-start section plus the full 40-cell matrix and
    return the complete report.

    Kept separate from `main()` so a test can call this with a tiny
    `repetitions` value without touching the filesystem beyond what the
    real subprocess harness itself requires — mirroring the identical
    `build_report()`/`main()` split every other runner in this
    repository already uses, for the identical reason: this is a real-
    process, real-model, multi-minute operation that has no place in a
    test suite's default run.
    """
    log_root = _fresh_process_log_dir()
    _logger.info("raw process logs for this run: %s", log_root)
    cold_start_ms = _measure_cold_start(log_root)
    with running_gateway_and_mock(log_root / "steady_state") as (gateway, _mock):
        cells = _run_matrix(gateway.base_url, gateway.stderr_log_path, repetitions, request_timeout_s)

    return LatencyReport(
        commit=_current_commit_hash(),
        concurrency_levels=list(CONCURRENCY_LEVELS),
        steady_state_repetitions=repetitions,
        request_timeout_s=request_timeout_s,
        cold_start_repetitions=COLD_START_REPETITIONS,
        cold_start_ms=cold_start_ms,
        cells=cells,
        caveat=_CAVEAT,
    )


def run_pilot(repetitions: int, request_timeout_s: float = DEFAULT_REQUEST_TIMEOUT_S) -> None:
    """Run the full 40-cell matrix at `PILOT_REPETITIONS` per cell,
    log each cell's mean latency (and any timeouts/errors), and project
    the full run's wall-clock time by scaling the pilot's own measured
    elapsed time by the repetition-count ratio. Writes no artifact —
    purely a human-facing estimate for deciding `--repetitions` (and,
    now, `--request-timeout`) before a real committed run.
    """
    log_root = _fresh_process_log_dir()
    _logger.info("raw process logs for this pilot run: %s", log_root)
    with running_gateway_and_mock(log_root / "pilot") as (gateway, _mock):
        start = time.perf_counter()
        cells = _run_matrix(
            gateway.base_url, gateway.stderr_log_path, PILOT_REPETITIONS, request_timeout_s
        )
        pilot_elapsed_s = time.perf_counter() - start

    for cell in cells:
        ttft_mean = cell["ttft_with_window_ms"]["mean"] if cell["ttft_with_window_ms"] else float("nan")
        total_mean = cell["total_latency_ms"]["mean"] if cell["total_latency_ms"] else float("nan")
        _logger.info(
            "pilot workload=%s concurrency=%d mean_ttft_with_window_ms=%.1f "
            "mean_total_latency_ms=%.1f n=%d timeout=%d error=%d",
            cell["workload"],
            cell["concurrency"],
            ttft_mean,
            total_mean,
            cell["n"],
            cell["timeout_count"],
            cell["error_count"],
        )
    scale = (repetitions + WARMUP_REPETITIONS) / (PILOT_REPETITIONS + WARMUP_REPETITIONS)
    projected_s = pilot_elapsed_s * scale
    _logger.info(
        "pilot: %.1fs for n=%d/cell across %d cells (request_timeout=%.0fs); projected full "
        "run at --repetitions=%d: ~%.1fs (~%.1f min)",
        pilot_elapsed_s,
        PILOT_REPETITIONS,
        len(cells),
        request_timeout_s,
        repetitions,
        projected_s,
        projected_s / 60,
    )


def _format_stats(stats: StatsSummary | None) -> str:
    if stats is None:
        return "n/a"
    return f"{stats['mean']:.1f} / {stats['p95']:.1f} / {stats['p99']:.1f} (cv={stats['cv']:.2f})"


def render_markdown(report: LatencyReport) -> str:
    """Render `report` as markdown — a pure function of the report
    data, regenerable from a committed `latest.json` alone (mirroring
    every other runner's identical split)."""
    lines = [
        "# Phase 7 Latency Harness Results",
        "",
        f"Commit: `{report['commit']}`",
        f"Concurrency levels: {', '.join(str(c) for c in report['concurrency_levels'])}",
        f"Steady-state repetitions per cell: {report['steady_state_repetitions']} "
        f"(+{WARMUP_REPETITIONS} warm-up, discarded)",
        f"Per-request timeout: {report['request_timeout_s']:.0f}s",
        "",
        f"> {report['caveat']}",
        "",
        "## Cold start",
        "",
        f"n={report['cold_start_repetitions']} fresh processes. mean / p95 / p99 (cv) in ms, "
        "min / max also available in the JSON artifact. A small n makes p95/p99 here "
        "indicative only, not statistically robust.",
        "",
        f"`{_format_stats(report['cold_start_ms'])}` ms "
        f"(min={report['cold_start_ms']['min']:.1f}, max={report['cold_start_ms']['max']:.1f})",
        "",
        "## Per-workload, per-concurrency results",
        "",
        "Each latency column reports `mean / p95 / p99 (cv)` in ms, computed only over "
        "requests that actually completed (`n`) -- `timeout`/`error` counts are reported "
        "alongside, never folded into the percentiles. `tier_hit` is a categorical "
        "distribution over completed requests only.",
        "",
    ]

    cells_by_workload: dict[str, list[CellReport]] = {}
    for cell in report["cells"]:
        cells_by_workload.setdefault(cell["workload"], []).append(cell)

    for workload in WORKLOADS:
        workload_cells = cells_by_workload.get(workload.name, [])
        lines.append(f"### {workload.name}")
        lines.append("")
        lines.append(workload.description)
        lines.append("")
        lines.append(
            "| Concurrency | n (attempted) | timeout | error | TTFT (with window) | "
            "TTFT (without window) | Window tax (ms) | Window tax (%) | Total latency | "
            "Tier hit |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for cell in sorted(workload_cells, key=lambda c: c["concurrency"]):
            tier_hit = ", ".join(
                f"{klass}={fraction:.2f}" for klass, fraction in sorted(cell["tier_hit"].items())
            ) or "n/a"
            lines.append(
                f"| {cell['concurrency']} | {cell['n']} ({cell['attempted']}) | "
                f"{cell['timeout_count']} | {cell['error_count']} | "
                f"{_format_stats(cell['ttft_with_window_ms'])} | "
                f"{_format_stats(cell['ttft_without_window_ms'])} | "
                f"{_format_stats(cell['window_tax_ms'])} | "
                f"{_format_stats(cell['window_tax_percent'])} | "
                f"{_format_stats(cell['total_latency_ms'])} | {tier_hit} |"
            )
        lines.append("")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repetitions",
        type=int,
        default=DEFAULT_STEADY_STATE_REPETITIONS,
        help="Steady-state repetitions per cell (default: %(default)s).",
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=DEFAULT_REQUEST_TIMEOUT_S,
        help=(
            "Per-request httpx timeout in seconds, applied to connect/read/write/pool "
            "alike (default: %(default)s). A request that exceeds this is recorded as a "
            "timeout in that cell's timeout_count, not raised as a fatal error -- see "
            "measure.DEFAULT_REQUEST_TIMEOUT_S for why 120s is a starting point, not a "
            "guarantee, for every cell in the matrix."
        ),
    )
    parser.add_argument(
        "--pilot-only",
        action="store_true",
        help=(
            "Run a small calibration pass (n=%d/cell) and print a wall-clock "
            "projection for --repetitions; writes no artifact." % PILOT_REPETITIONS
        ),
    )
    args = parser.parse_args()

    if args.pilot_only:
        run_pilot(args.repetitions, args.request_timeout)
        return

    report = build_report(repetitions=args.repetitions, request_timeout_s=args.request_timeout)
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    _JSON_PATH.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    _MARKDOWN_PATH.write_text(render_markdown(report), encoding="utf-8")
    _logger.info("wrote %s and %s", _JSON_PATH, _MARKDOWN_PATH)


if __name__ == "__main__":
    main()
