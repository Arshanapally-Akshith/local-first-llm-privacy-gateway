"""benchmarks.scoring.score: `score_example()`, `aggregate_scores()`,
and `score_arm()` — fast, using hand-built `GoldEntity`/`Prediction`
fixtures and a fake `Arm`, no real detector or model involved. The
real-data, real-arm proof lives in
`tests/integration/test_scoring_real_arm.py`.
"""

from src.core.types import Offset

from benchmarks.arms.arm import Prediction
from benchmarks.generate.dataset_types import BenchmarkExample, GoldEntity
from benchmarks.scoring.score import aggregate_scores, score_arm, score_example
from benchmarks.scoring.types import ConfusionCounts


def _gold(start: int, end: int, entity_type: str, value: str) -> GoldEntity:
    return GoldEntity(start=Offset(start), end=Offset(end), entity_type=entity_type, value=value)  # type: ignore[arg-type]


def _prediction(start: int, end: int, entity_type: str) -> Prediction:
    return Prediction(start=Offset(start), end=Offset(end), entity_type=entity_type)  # type: ignore[arg-type]


def test_exact_match_is_one_true_positive() -> None:
    gold = [_gold(0, 4, "PAN", "ABCD")]
    predictions = [_prediction(0, 4, "PAN")]
    scores = score_example(gold, predictions)
    assert scores == {"PAN": ConfusionCounts(true_positives=1, false_positives=0, false_negatives=0)}


def test_missed_gold_entity_is_a_false_negative() -> None:
    gold = [_gold(0, 4, "PAN", "ABCD")]
    predictions: list[Prediction] = []
    scores = score_example(gold, predictions)
    assert scores == {"PAN": ConfusionCounts(true_positives=0, false_positives=0, false_negatives=1)}


def test_hallucinated_prediction_is_a_false_positive() -> None:
    gold: list[GoldEntity] = []
    predictions = [_prediction(0, 4, "PAN")]
    scores = score_example(gold, predictions)
    assert scores == {"PAN": ConfusionCounts(true_positives=0, false_positives=1, false_negatives=0)}


def test_right_offset_wrong_type_is_a_miss_for_both_types() -> None:
    # The gold type gets a false negative (it was never predicted, as
    # far as its own type is concerned), and the predicted type gets a
    # false positive (nothing of that type was actually there) - a
    # right-place-wrong-label guess is not partial credit under the
    # exact-type criterion.
    gold = [_gold(0, 10, "PAN", "ABCDE1234F")]
    predictions = [_prediction(0, 10, "CARD")]
    scores = score_example(gold, predictions)
    assert scores == {
        "PAN": ConfusionCounts(true_positives=0, false_positives=0, false_negatives=1),
        "CARD": ConfusionCounts(true_positives=0, false_positives=1, false_negatives=0),
    }


def test_slightly_wrong_offset_is_a_full_miss_not_partial_credit() -> None:
    gold = [_gold(0, 10, "PAN", "ABCDE1234F")]
    predictions = [_prediction(0, 9, "PAN")]  # one character short
    scores = score_example(gold, predictions)
    assert scores == {"PAN": ConfusionCounts(true_positives=0, false_positives=1, false_negatives=1)}


def test_duplicate_prediction_credits_once_and_counts_the_extra_as_a_false_positive() -> None:
    # The one-to-one rule from docs/DECISIONS.md (2026-07-22): at most
    # one predicted span may be credited against a given gold span.
    gold = [_gold(0, 4, "PAN", "ABCD")]
    predictions = [_prediction(0, 4, "PAN"), _prediction(0, 4, "PAN")]
    scores = score_example(gold, predictions)
    assert scores == {"PAN": ConfusionCounts(true_positives=1, false_positives=1, false_negatives=0)}


def test_two_distinct_gold_entities_of_the_same_type_are_scored_independently() -> None:
    gold = [_gold(0, 4, "PAN", "ABCD"), _gold(10, 14, "PAN", "WXYZ")]
    predictions = [_prediction(0, 4, "PAN")]  # only the first one found
    scores = score_example(gold, predictions)
    assert scores == {"PAN": ConfusionCounts(true_positives=1, false_positives=0, false_negatives=1)}


def test_multiple_entity_types_in_one_example_are_scored_independently() -> None:
    gold = [_gold(0, 4, "PAN", "ABCD"), _gold(10, 22, "AADHAAR", "999941057058")]
    predictions = [_prediction(0, 4, "PAN")]  # AADHAAR missed entirely
    scores = score_example(gold, predictions)
    assert scores == {
        "PAN": ConfusionCounts(true_positives=1, false_positives=0, false_negatives=0),
        "AADHAAR": ConfusionCounts(true_positives=0, false_positives=0, false_negatives=1),
    }


def test_empty_gold_and_empty_predictions_returns_an_empty_dict() -> None:
    assert score_example([], []) == {}


def test_aggregate_scores_sums_across_examples() -> None:
    per_example = [
        {"PAN": ConfusionCounts(true_positives=1, false_positives=0, false_negatives=0)},
        {"PAN": ConfusionCounts(true_positives=0, false_positives=1, false_negatives=1)},
        {"AADHAAR": ConfusionCounts(true_positives=1, false_positives=0, false_negatives=0)},
    ]
    totals = aggregate_scores(per_example)
    assert totals == {
        "PAN": ConfusionCounts(true_positives=1, false_positives=1, false_negatives=1),
        "AADHAAR": ConfusionCounts(true_positives=1, false_positives=0, false_negatives=0),
    }


def test_aggregate_scores_handles_an_empty_iterable() -> None:
    assert aggregate_scores([]) == {}


class _FakeArm:
    """A minimal `Arm` (see `benchmarks/arms/arm.py`), no real detector
    or model - predicts a fixed set of spans regardless of `text`, so
    `score_arm()`'s own orchestration (iterate examples, call predict,
    aggregate) can be tested deterministically and fast."""

    def __init__(self, fixed_predictions: dict[str, list[Prediction]]) -> None:
        self._fixed_predictions = fixed_predictions

    def predict(self, text: str) -> list[Prediction]:
        return self._fixed_predictions.get(text, [])


def test_score_arm_runs_every_example_and_aggregates() -> None:
    examples = (
        BenchmarkExample(
            example_id="ex-1",
            template_id="t1",
            language="en",
            text="My PAN is ABCDE1234F.",
            entities=(_gold(11, 21, "PAN", "ABCDE1234F"),),
        ),
        BenchmarkExample(
            example_id="ex-2",
            template_id="t2",
            language="en",
            text="No PII here.",
            entities=(),
        ),
    )
    arm = _FakeArm({"My PAN is ABCDE1234F.": [_prediction(11, 21, "PAN")]})
    report = score_arm(examples, arm)
    assert report["PAN"].precision == 1.0
    assert report["PAN"].recall == 1.0
    assert report["PAN"].support == 1


def test_score_arm_on_an_empty_example_sequence_returns_an_empty_report() -> None:
    arm = _FakeArm({})
    assert score_arm((), arm) == {}
