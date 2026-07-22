"""benchmarks.arms.presidio_custom.engine.own_vocabulary(): derives the
"which labels are ours" set directly from a list of recognizers, rather
than a separately hand-maintained tuple - fast, no engine/model needed."""

from benchmarks.arms.presidio_custom.engine import own_vocabulary
from benchmarks.arms.presidio_custom.recognizers import build_custom_recognizers


def test_matches_the_five_tier1_custom_recognizer_types() -> None:
    assert own_vocabulary(build_custom_recognizers()) == {
        "AADHAAR",
        "PAN",
        "IFSC",
        "UPI",
        "VEHICLE_REG",
    }


def test_empty_recognizer_list_gives_an_empty_set() -> None:
    assert own_vocabulary([]) == frozenset()
