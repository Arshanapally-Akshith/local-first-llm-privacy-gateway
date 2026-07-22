"""benchmarks.scoring.types: `ConfusionCounts` addition and
`EntityTypeReport`'s derived precision/recall/F1 — fast, no examples or
arms involved."""

import pytest

from benchmarks.scoring.types import ConfusionCounts, EntityTypeReport


def test_confusion_counts_add_sums_each_field() -> None:
    a = ConfusionCounts(true_positives=3, false_positives=1, false_negatives=2)
    b = ConfusionCounts(true_positives=5, false_positives=0, false_negatives=1)
    total = a + b
    assert total == ConfusionCounts(true_positives=8, false_positives=1, false_negatives=3)


def test_confusion_counts_add_rejects_a_non_confusion_counts_operand() -> None:
    with pytest.raises(TypeError):
        ConfusionCounts(1, 0, 0) + 5  # type: ignore[operator]


def test_precision_recall_f1_from_known_counts() -> None:
    # 8 correct, 2 false alarms, 2 missed.
    report = EntityTypeReport(
        entity_type="PAN",
        counts=ConfusionCounts(true_positives=8, false_positives=2, false_negatives=2),
    )
    assert report.precision == pytest.approx(0.8)
    assert report.recall == pytest.approx(0.8)
    assert report.f1 == pytest.approx(0.8)
    assert report.support == 10


def test_precision_is_zero_when_nothing_was_predicted() -> None:
    report = EntityTypeReport(
        entity_type="AADHAAR",
        counts=ConfusionCounts(true_positives=0, false_positives=0, false_negatives=5),
    )
    assert report.precision == 0.0
    assert report.recall == 0.0
    assert report.f1 == 0.0
    assert report.support == 5


def test_recall_is_zero_when_there_is_no_support() -> None:
    report = EntityTypeReport(
        entity_type="ORG",
        counts=ConfusionCounts(true_positives=0, false_positives=3, false_negatives=0),
    )
    assert report.support == 0
    assert report.recall == 0.0
    assert report.precision == 0.0  # 0 true positives, 3 false positives


def test_perfect_score() -> None:
    report = EntityTypeReport(
        entity_type="CARD",
        counts=ConfusionCounts(true_positives=10, false_positives=0, false_negatives=0),
    )
    assert report.precision == 1.0
    assert report.recall == 1.0
    assert report.f1 == 1.0
