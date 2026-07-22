"""benchmarks.arms.presidio_custom.recognizers: `DetectorBackedRecognizer`
and `build_custom_recognizers()` — fast tests, deliberately independent
of `AnalyzerEngine`/spaCy: these recognizers delegate entirely to the
real Tier-1 `Detector` classes (regex + checksum, no NLP model), so
proving they work correctly needs no model load at all. The
`nlp_artifacts`/`entities` parameters `analyze()` receives from a real
`AnalyzerEngine` are unused by design (see the class's own docstring) -
tests below pass placeholder values for them directly.

Synthetic entity values reuse `benchmarks.generate.entity_values` (Phase
5 Task 2) rather than hand-typed fixtures: every value it produces is
already proven, by that task's own test suite, to be checksum/structurally
valid and real-detector-detectable — reusing it here means a typo in a
hand-written fixture value can never be the reason one of these tests
passes or fails.
"""

import random

from src.detect.tier1.aadhaar import AadhaarDetector
from src.detect.tier1.ifsc import IfscDetector
from src.detect.tier1.pan import PanDetector
from src.detect.tier1.upi import UpiDetector
from src.detect.tier1.vehicle_registration import VehicleRegistrationDetector

from benchmarks.arms.presidio_custom.recognizers import (
    DetectorBackedRecognizer,
    build_custom_recognizers,
)
from benchmarks.generate.entity_values import generate_value

_DETECTORS_BY_TYPE = {
    "AADHAAR": AadhaarDetector,
    "PAN": PanDetector,
    "IFSC": IfscDetector,
    "UPI": UpiDetector,
    "VEHICLE_REG": VehicleRegistrationDetector,
}


def test_build_custom_recognizers_returns_exactly_the_five_types_presidio_lacks() -> None:
    recognizers = build_custom_recognizers()
    assert {r.supported_entities[0] for r in recognizers} == set(_DETECTORS_BY_TYPE)
    assert len(recognizers) == 5


def test_each_recognizer_detects_its_own_synthetic_value_with_score_1() -> None:
    for entity_type, detector_cls in _DETECTORS_BY_TYPE.items():
        value = generate_value(entity_type, random.Random(0))
        recognizer = DetectorBackedRecognizer(detector_cls())
        results = recognizer.analyze(value, entities=[], nlp_artifacts=None)
        assert len(results) == 1
        result = results[0]
        assert result.entity_type == entity_type
        assert result.start == 0
        assert result.end == len(value)
        assert result.score == 1.0


def test_recognizer_returns_empty_list_for_text_with_no_matching_entity() -> None:
    recognizer = DetectorBackedRecognizer(AadhaarDetector())
    assert recognizer.analyze("no PII here at all", entities=[], nlp_artifacts=None) == []


def test_recognizer_finds_its_entity_embedded_in_a_larger_sentence() -> None:
    value = generate_value("PAN", random.Random(1))
    text = f"Please update my PAN {value} in the records."
    recognizer = DetectorBackedRecognizer(PanDetector())
    results = recognizer.analyze(text, entities=[], nlp_artifacts=None)
    assert len(results) == 1
    assert text[results[0].start : results[0].end] == value


def test_recognizer_load_is_a_no_op_and_does_not_raise() -> None:
    DetectorBackedRecognizer(AadhaarDetector()).load()
