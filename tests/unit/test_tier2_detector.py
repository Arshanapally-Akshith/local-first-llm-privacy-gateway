"""Tier2Detector / Tier2Model: the Phase 4 Task 1 seam.

Everything here runs against a fake `Tier2Model` — no real model is
chosen yet (Phase 4 Task 2 is a separate, later task), and per
CLAUDE.md's dependency-injection rule, nothing above this seam should
need one to be testable at all.
"""

import pytest

from src.core.exceptions import DetectionError
from src.core.types import EntityType, Offset
from src.detect.registry import get_tier2_detectors
from src.detect.tier2.detector import Tier2Detector
from src.detect.tier2.model import ModelEntityMatch


class _FakeTier2Model:
    """Returns a fixed set of matches regardless of `text`, and records
    every call so tests can prove sharing/call-count behaviour without
    needing a real model's timing or output to reason about."""

    def __init__(self, matches: list[ModelEntityMatch]) -> None:
        self._matches = matches
        self.call_texts: list[str] = []

    def find_entities(self, text: str) -> list[ModelEntityMatch]:
        self.call_texts.append(text)
        return self._matches


def _match(start: int, end: int, entity_type: EntityType) -> ModelEntityMatch:
    return ModelEntityMatch(start=Offset(start), end=Offset(end), entity_type=entity_type)


def test_detect_keeps_only_matches_of_its_own_entity_type() -> None:
    model = _FakeTier2Model(
        [_match(0, 5, "PERSON"), _match(7, 10, "ORG"), _match(12, 19, "ADDRESS")]
    )
    detector = Tier2Detector(entity_type="PERSON", model=model)

    spans = detector.detect("Ramesh works at Acme in Delhi")

    assert len(spans) == 1
    assert spans[0].start == 0
    assert spans[0].end == 5
    assert spans[0].entity_type == "PERSON"
    assert spans[0].tier == 2


def test_detect_returns_empty_list_when_model_finds_nothing() -> None:
    detector = Tier2Detector(entity_type="ORG", model=_FakeTier2Model([]))

    assert detector.detect("nothing interesting here") == []


def test_detect_returns_empty_list_when_model_finds_only_other_types() -> None:
    model = _FakeTier2Model([_match(0, 5, "PERSON")])
    detector = Tier2Detector(entity_type="ADDRESS", model=model)

    assert detector.detect("Ramesh") == []


@pytest.mark.parametrize(
    "start,end,text",
    [
        (-1, 3, "abc"),  # negative start
        (2, 2, "abcdef"),  # start == end
        (3, 2, "abcdef"),  # start > end
        (0, 10, "abc"),  # end past len(text)
    ],
)
def test_detect_raises_detection_error_for_out_of_bounds_offsets(
    start: int, end: int, text: str
) -> None:
    model = _FakeTier2Model([_match(start, end, "PERSON")])
    detector = Tier2Detector(entity_type="PERSON", model=model)

    with pytest.raises(DetectionError):
        detector.detect(text)


def test_detection_error_message_never_contains_the_text() -> None:
    secret_text = "Ramesh Kumar's Aadhaar is 234567890124"
    model = _FakeTier2Model([_match(0, 100, "PERSON")])
    detector = Tier2Detector(entity_type="PERSON", model=model)

    with pytest.raises(DetectionError) as exc_info:
        detector.detect(secret_text)

    assert "Ramesh" not in str(exc_info.value)
    assert "234567890124" not in str(exc_info.value)


def test_matches_of_a_different_type_do_not_trigger_offset_validation() -> None:
    """An out-of-bounds match for a type this detector doesn't care
    about must not raise here — it's a different `Tier2Detector`
    instance's problem, not this one's, since each detector only
    validates the matches it actually keeps."""
    model = _FakeTier2Model([_match(0, 999, "ORG")])
    detector = Tier2Detector(entity_type="PERSON", model=model)

    assert detector.detect("short text") == []


def test_three_detectors_share_the_same_injected_model_instance() -> None:
    model = _FakeTier2Model(
        [_match(0, 6, "PERSON"), _match(10, 14, "ORG"), _match(18, 23, "ADDRESS")]
    )
    person = Tier2Detector(entity_type="PERSON", model=model)
    org = Tier2Detector(entity_type="ORG", model=model)
    address = Tier2Detector(entity_type="ADDRESS", model=model)

    text = "Ramesh met Acme staff at Delhi"
    person.detect(text)
    org.detect(text)
    address.detect(text)

    # Same model instance called once per detector, each with the exact
    # same text - proving the sharing is real, not three independent
    # model copies each doing their own thing.
    assert model.call_texts == [text, text, text]


def test_get_tier2_detectors_returns_one_per_phase_4_entity_type() -> None:
    model = _FakeTier2Model([])

    detectors = get_tier2_detectors(model)

    assert {d.entity_type for d in detectors} == {"PERSON", "ORG", "ADDRESS"}
    assert all(d.tier == 2 for d in detectors)


def test_get_tier2_detectors_shares_one_model_across_all_three() -> None:
    model = _FakeTier2Model([_match(0, 3, "PERSON")])

    detectors = get_tier2_detectors(model)
    for detector in detectors:
        detector.detect("abc")

    assert len(model.call_texts) == 3
    assert all(text == "abc" for text in model.call_texts)


def test_get_tier2_detectors_called_twice_returns_independent_but_equivalent_sets() -> None:
    """Not cached (see registry.py's own docstring) - each call builds
    fresh, cheap wrapper objects, still sharing whichever model was
    passed in."""
    model = _FakeTier2Model([])

    first = get_tier2_detectors(model)
    second = get_tier2_detectors(model)

    assert {d.entity_type for d in first} == {d.entity_type for d in second}
