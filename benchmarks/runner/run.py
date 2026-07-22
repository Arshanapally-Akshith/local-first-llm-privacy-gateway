"""The Phase 5 benchmark runner entrypoint.

Run with:
    python -m benchmarks.runner.run

Writes `benchmarks/results/latest.json` (the authoritative, full-
precision artifact — every number a future README table could ever
need, stamped with the commit that produced it) and
`benchmarks/results/latest.md` (a markdown rendering of the same data,
regenerable purely from the JSON artifact — see `render_markdown()`).
Neither file is hand-edited; deleting both and re-running this module
must reproduce them (BUILD.md's Phase 5 gate, applied to the results
artifact the way `benchmarks/generate/build_dataset.py` already applies
the same discipline to the dataset itself).

This module does **not** write to a top-level `README.md` — no such
file exists yet in this repository, and assembling the polished,
public-facing README (pitch, GIF, competitors, threat model) is
explicitly BUILD.md's Phase 8 scope, not Phase 5's. What Phase 5 owns is
the *mechanism*: a deterministic, from-scratch-reproducible markdown
table with nothing written by hand, ready for Phase 8 to embed.
"""

import json
import logging
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final, TypedDict

from benchmarks.arms.arm import Arm
from benchmarks.arms.ours import OurCascadeArm
from benchmarks.arms.presidio_custom.engine import PresidioCustomArm
from benchmarks.arms.presidio_gliner.engine import PresidioGlinerArm
from benchmarks.arms.presidio_stock import PresidioStockArm
from benchmarks.generate.build_dataset import build_dataset
from benchmarks.generate.dataset_types import BenchmarkExample
from benchmarks.scoring.score import score_arm
from benchmarks.scoring.types import EntityTypeReport

_logger = logging.getLogger("benchmarks.runner")
_logger.setLevel(logging.INFO)
_logger.addHandler(logging.StreamHandler())

_RESULTS_DIR: Final[Path] = Path(__file__).resolve().parent.parent / "results"
_JSON_PATH: Final[Path] = _RESULTS_DIR / "latest.json"
_MARKDOWN_PATH: Final[Path] = _RESULTS_DIR / "latest.md"

_ARM_FACTORIES: Final[list[tuple[str, str, Callable[[], Arm]]]] = [
    ("presidio_stock", "Arm 1 -- Presidio (stock)", PresidioStockArm),
    ("presidio_custom", "Arm 2 -- Presidio + custom recognizers", PresidioCustomArm),
    (
        "presidio_gliner",
        "Arm 3 -- Presidio + custom recognizers + GLiNER backend",
        PresidioGlinerArm,
    ),
    ("ours", "Arm 4 -- Our cascade", OurCascadeArm),
]
"""`(key, display_title, factory)` for each arm, in BUILD.md's own
numbering order. `key` is the stable JSON field name; `display_title`
is only ever used for the markdown rendering. Arms are constructed
lazily, one at a time (`build_report()`), not all four up front — each
Presidio/GLiNER-backed arm loads real model weights at construction,
and there is no reason to hold more than one arm's models in memory at
once during a sequential run."""


class EntityTypeSummary(TypedDict):
    precision: float
    recall: float
    f1: float
    support: int
    true_positives: int
    false_positives: int
    false_negatives: int


class BenchmarkReport(TypedDict):
    commit: str
    dataset_size: int
    arms: dict[str, dict[str, EntityTypeSummary]]


def _entity_type_summary(report: EntityTypeReport) -> EntityTypeSummary:
    return {
        "precision": report.precision,
        "recall": report.recall,
        "f1": report.f1,
        "support": report.support,
        "true_positives": report.counts.true_positives,
        "false_positives": report.counts.false_positives,
        "false_negatives": report.counts.false_negatives,
    }


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


def build_report(examples: Sequence[BenchmarkExample] | None = None) -> BenchmarkReport:
    """Run every arm over `examples` (the full committed dataset if
    omitted) and return the full report.

    Kept separate from `main()` so tests can pass a small `examples`
    sample without touching the filesystem or invoking git — mirroring
    `rehydration_fidelity/runner/run.py::build_report()`'s identical
    split, and for the identical reason: running all four arms over the
    full ~2,860-example dataset is a real-model, multi-hour operation
    (two of the four arms run GLiNER inference once per example) that
    has no place in a test suite's default run.
    """
    if examples is None:
        examples = build_dataset()

    arms_results: dict[str, dict[str, EntityTypeSummary]] = {}
    for key, title, factory in _ARM_FACTORIES:
        _logger.info("running arm=%s (%s)", key, title)
        arm = factory()
        per_type = score_arm(examples, arm)
        arms_results[key] = {
            entity_type: _entity_type_summary(entity_report)
            for entity_type, entity_report in per_type.items()
        }
        _logger.info("finished arm=%s", key)

    return {
        "commit": _current_commit_hash(),
        "dataset_size": len(examples),
        "arms": arms_results,
    }


def render_markdown(report: BenchmarkReport) -> str:
    """Render `report` as a markdown table per arm — a pure function of
    the report data, so a future reader (or test) can regenerate this
    exact text from a committed `latest.json` alone, without re-running
    any arm.
    """
    arm_titles = {key: title for key, title, _factory in _ARM_FACTORIES}
    lines = [
        "# Phase 5 Benchmark Results",
        "",
        f"Commit: `{report['commit']}`",
        "",
        f"Dataset size: {report['dataset_size']} examples "
        "(`benchmarks/data/dataset.jsonl` — see `benchmarks/data/DATASET_CARD.md`)",
        "",
        "Per-entity precision / recall / F1, exact-span exact-type criterion "
        "(`docs/DECISIONS.md`, 2026-07-22). Rows where a baseline beats another "
        "arm are not removed.",
        "",
    ]
    for key, _title, _factory in _ARM_FACTORIES:
        lines.append(f"## {arm_titles[key]}")
        lines.append("")
        lines.append("| Entity Type | Precision | Recall | F1 | Support |")
        lines.append("|---|---|---|---|---|")
        for entity_type in sorted(report["arms"][key]):
            summary = report["arms"][key][entity_type]
            lines.append(
                f"| {entity_type} | {summary['precision']:.3f} | {summary['recall']:.3f} | "
                f"{summary['f1']:.3f} | {summary['support']} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    report = build_report()
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    _JSON_PATH.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    _MARKDOWN_PATH.write_text(render_markdown(report), encoding="utf-8")
    _logger.info("wrote %s and %s", _JSON_PATH, _MARKDOWN_PATH)


if __name__ == "__main__":
    main()
