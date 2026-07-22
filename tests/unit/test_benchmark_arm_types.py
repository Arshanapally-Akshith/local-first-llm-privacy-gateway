"""benchmarks.arms.arm: the `Prediction` type's own offset invariant —
mirrors `tests/unit/test_span.py`'s and
`tests/unit/test_benchmark_build_dataset.py`'s equivalent coverage for
`Span` and `GoldEntity`, applied to the third type in this project that
shares the same `(start, end, entity_type)` shape for a different
reason."""

import pytest

from src.core.types import Offset

from benchmarks.arms.arm import Prediction


def test_valid_prediction_constructs() -> None:
    prediction = Prediction(start=Offset(0), end=Offset(4), entity_type="PAN")
    assert prediction.start == 0
    assert prediction.end == 4
    assert prediction.entity_type == "PAN"


def test_end_equal_to_start_raises() -> None:
    with pytest.raises(ValueError, match="start must be >= 0 and end must be > start"):
        Prediction(start=Offset(4), end=Offset(4), entity_type="PAN")


def test_end_before_start_raises() -> None:
    with pytest.raises(ValueError):
        Prediction(start=Offset(5), end=Offset(2), entity_type="PAN")


def test_negative_start_raises() -> None:
    with pytest.raises(ValueError):
        Prediction(start=Offset(-1), end=Offset(2), entity_type="PAN")


def test_prediction_is_frozen() -> None:
    prediction = Prediction(start=Offset(0), end=Offset(1), entity_type="EMAIL")
    with pytest.raises(AttributeError):
        prediction.start = Offset(5)  # type: ignore[misc]
