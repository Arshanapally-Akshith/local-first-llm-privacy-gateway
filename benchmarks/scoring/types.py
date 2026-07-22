"""Scoring result types: raw counts (`ConfusionCounts`), and the
per-entity-type report derived from them (`EntityTypeReport`).

Kept as two separate types, not one: `ConfusionCounts` is what gets
summed across examples (`score.py::aggregate_scores()`) — it must stay
pure data with no derived state, so adding counts from two examples is
just field-wise addition. `EntityTypeReport` is a read-only *view* over
a finished, fully-aggregated `ConfusionCounts` — precision/recall/F1 are
computed properties, never stored, so they can never silently go stale
relative to the counts they were derived from.
"""

from dataclasses import dataclass

from src.core.types import EntityType


@dataclass(frozen=True, slots=True)
class ConfusionCounts:
    """Raw true/false-positive/negative counts for one entity type,
    under the exact-span, exact-type criterion — summable across
    examples via `+`.
    """

    true_positives: int
    false_positives: int
    false_negatives: int

    def __add__(self, other: "ConfusionCounts") -> "ConfusionCounts":
        if not isinstance(other, ConfusionCounts):
            return NotImplemented
        return ConfusionCounts(
            true_positives=self.true_positives + other.true_positives,
            false_positives=self.false_positives + other.false_positives,
            false_negatives=self.false_negatives + other.false_negatives,
        )


@dataclass(frozen=True, slots=True)
class EntityTypeReport:
    """Precision/recall/F1 for one entity type, derived from a finished
    `ConfusionCounts` — typically one already aggregated across an
    entire dataset for one arm.
    """

    entity_type: EntityType
    counts: ConfusionCounts

    @property
    def support(self) -> int:
        """The number of gold entities of this type — `true_positives +
        false_negatives`, the standard classification-report meaning of
        "support": how many real instances existed to be found,
        independent of how many the arm actually predicted."""
        return self.counts.true_positives + self.counts.false_negatives

    @property
    def precision(self) -> float:
        """`0.0` when nothing of this type was ever predicted
        (`true_positives + false_positives == 0`) — a defined, reported
        value rather than a raised `ZeroDivisionError`, since "predicted
        nothing" is a normal, common outcome for a type an arm has no
        recognizer for at all (e.g. arm 1 on `AADHAAR`), not an
        exceptional one."""
        denominator = self.counts.true_positives + self.counts.false_positives
        return self.counts.true_positives / denominator if denominator else 0.0

    @property
    def recall(self) -> float:
        """`0.0` when `support == 0` (no gold entity of this type
        existed at all) — does not occur for any type in the committed
        Phase 5 dataset (every type has non-zero support,
        `benchmarks/data/DATASET_CARD.md`), but is handled here rather
        than assumed, since this function has no way to know which
        dataset it is being asked to score."""
        denominator = self.counts.true_positives + self.counts.false_negatives
        return self.counts.true_positives / denominator if denominator else 0.0

    @property
    def f1(self) -> float:
        """The harmonic mean of `precision` and `recall`, `0.0` when
        both are `0.0` (the only case `precision + recall == 0` can
        occur, since neither is ever negative)."""
        precision, recall = self.precision, self.recall
        denominator = precision + recall
        return 2 * precision * recall / denominator if denominator else 0.0
