"""Scores one example, or a whole arm across a dataset, under the
exact-span, exact-type criterion (`docs/DECISIONS.md`, 2026-07-22).

The one-to-one assignment rule that entry deferred to this task turns
out to need no bipartite-matching algorithm at all: because a match
requires *identical* `(start, end, entity_type)`, not merely an
overlap, two spans either match exactly or they do not — there is no
"which of several plausible candidates should this gold span match"
question the way there would be under a fuzzy or token-level criterion.
"Matching" a multiset of gold spans against a multiset of predicted
spans is therefore exactly the counting problem `collections.Counter`
already solves: for each distinct `(start, end, entity_type)` key, the
number of true positives is `min(gold_count, predicted_count)` for that
key, any predicted excess beyond that is a false positive, and any gold
shortfall is a false negative. This is what "at most one predicted span
may be credited against a given gold span... any others are counted as
false positives" (the 2026-07-22 entry's own phrasing) means computed
directly, not approximated.
"""

from collections import Counter
from collections.abc import Iterable, Sequence
from typing import cast

from src.core.types import EntityType

from benchmarks.arms.arm import Arm, Prediction
from benchmarks.generate.dataset_types import BenchmarkExample, GoldEntity
from benchmarks.scoring.types import ConfusionCounts, EntityTypeReport

_MatchKey = tuple[int, int, str]


def score_example(
    gold: Sequence[GoldEntity], predictions: Sequence[Prediction]
) -> dict[EntityType, ConfusionCounts]:
    """Score one example's predictions against its gold entities.

    Returns one `ConfusionCounts` per entity type that appears in
    either `gold` or `predictions` for this example — a type present in
    neither simply has no entry, rather than an explicit zero-valued
    one; `aggregate_scores()` accumulates correctly regardless, since a
    missing key contributes nothing either way.
    """
    gold_counts: Counter[_MatchKey] = Counter(
        (entity.start, entity.end, entity.entity_type) for entity in gold
    )
    predicted_counts: Counter[_MatchKey] = Counter(
        (prediction.start, prediction.end, prediction.entity_type) for prediction in predictions
    )

    totals: dict[EntityType, list[int]] = {}
    for key in gold_counts.keys() | predicted_counts.keys():
        entity_type = cast(EntityType, key[2])
        gold_count = gold_counts[key]
        predicted_count = predicted_counts[key]
        true_positives = min(gold_count, predicted_count)
        bucket = totals.setdefault(entity_type, [0, 0, 0])
        bucket[0] += true_positives
        bucket[1] += predicted_count - true_positives  # false positives
        bucket[2] += gold_count - true_positives  # false negatives

    return {
        entity_type: ConfusionCounts(
            true_positives=counts[0], false_positives=counts[1], false_negatives=counts[2]
        )
        for entity_type, counts in totals.items()
    }


def aggregate_scores(
    per_example_scores: Iterable[dict[EntityType, ConfusionCounts]],
) -> dict[EntityType, ConfusionCounts]:
    """Sum `score_example()`'s output across every example in a
    dataset, per entity type."""
    totals: dict[EntityType, ConfusionCounts] = {}
    for scores in per_example_scores:
        for entity_type, counts in scores.items():
            totals[entity_type] = counts if entity_type not in totals else totals[entity_type] + counts
    return totals


def score_arm(
    examples: Sequence[BenchmarkExample], arm: Arm
) -> dict[EntityType, EntityTypeReport]:
    """Run `arm` over every example's text, score each against its own
    gold entities, and return one `EntityTypeReport` per entity type
    that appeared anywhere in `examples`' gold labels or `arm`'s
    predictions.
    """
    per_example_scores = [score_example(example.entities, arm.predict(example.text)) for example in examples]
    aggregated = aggregate_scores(per_example_scores)
    return {
        entity_type: EntityTypeReport(entity_type=entity_type, counts=counts)
        for entity_type, counts in aggregated.items()
    }
