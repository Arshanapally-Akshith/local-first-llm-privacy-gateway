"""benchmarks.runner.run: `render_markdown()` and `_entity_type_summary()`
— fast, pure-function tests using a hand-built `BenchmarkReport`, no
dataset, arm, or model involved. `build_report()`'s own orchestration
(real arms, real models) is proved in
`tests/integration/test_runner_real_run.py`.
"""

import pytest

from benchmarks.runner.run import BenchmarkReport, _entity_type_summary, render_markdown
from benchmarks.scoring.types import ConfusionCounts, EntityTypeReport


def _report(entity_type: str, tp: int, fp: int, fn: int) -> EntityTypeReport:
    return EntityTypeReport(
        entity_type=entity_type,  # type: ignore[arg-type]
        counts=ConfusionCounts(true_positives=tp, false_positives=fp, false_negatives=fn),
    )


def test_entity_type_summary_carries_every_field() -> None:
    summary = _entity_type_summary(_report("PAN", tp=8, fp=2, fn=2))
    assert summary["true_positives"] == 8
    assert summary["false_positives"] == 2
    assert summary["false_negatives"] == 2
    assert summary["support"] == 10
    assert summary["precision"] == 0.8
    assert summary["recall"] == 0.8
    assert summary["f1"] == pytest.approx(0.8)


_ONE_TYPE_ARM = {
    "AADHAAR": {
        "precision": 1.0,
        "recall": 1.0,
        "f1": 1.0,
        "support": 3,
        "true_positives": 3,
        "false_positives": 0,
        "false_negatives": 0,
    },
}

_FAKE_REPORT: BenchmarkReport = {
    "commit": "deadbeef",
    "dataset_size": 42,
    "arms": {
        "presidio_stock": {
            "CARD": {
                "precision": 1.0,
                "recall": 0.5,
                "f1": 0.6667,
                "support": 4,
                "true_positives": 2,
                "false_positives": 0,
                "false_negatives": 2,
            },
            "AADHAAR": {
                "precision": 0.0,
                "recall": 0.0,
                "f1": 0.0,
                "support": 3,
                "true_positives": 0,
                "false_positives": 0,
                "false_negatives": 3,
            },
        },
        "presidio_custom": _ONE_TYPE_ARM,
        "presidio_gliner": _ONE_TYPE_ARM,
        "ours": _ONE_TYPE_ARM,
    },
}


def test_render_markdown_includes_the_commit_and_dataset_size() -> None:
    text = render_markdown(_FAKE_REPORT)
    assert "deadbeef" in text
    assert "42 examples" in text


def test_render_markdown_includes_every_arm_and_entity_type() -> None:
    text = render_markdown(_FAKE_REPORT)
    assert "Arm 1" in text
    assert "Arm 4" in text
    assert "CARD" in text
    assert "AADHAAR" in text


def test_render_markdown_does_not_hide_a_zero_score_row() -> None:
    # BUILD.md: "Rows where a baseline beats us are present in the
    # table" - the weaker requirement this proves is that *no* row is
    # ever silently dropped, zero-scoring or not.
    text = render_markdown(_FAKE_REPORT)
    assert "| AADHAAR | 0.000 | 0.000 | 0.000 | 3 |" in text


def test_render_markdown_is_a_pure_function_of_the_report() -> None:
    assert render_markdown(_FAKE_REPORT) == render_markdown(_FAKE_REPORT)


def test_render_markdown_entity_rows_are_sorted_for_deterministic_output() -> None:
    text = render_markdown(_FAKE_REPORT)
    card_index = text.index("| CARD |")
    aadhaar_index = text.index("| AADHAAR |")
    assert aadhaar_index < card_index  # alphabetical within the presidio_stock section
