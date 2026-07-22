"""benchmarks.arms.presidio_custom: `PresidioCustomArm` — the real,
installed `AnalyzerEngine` extended with the five `DetectorBackedRecognizer`s.
`real_model`-marked, same reasoning as `test_presidio_stock_arm.py`.

The one property that matters most here, and gets its own test: arm 2
is additive over arm 1, never a replacement — everything arm 1 detects,
arm 2 must still detect, on top of the five new types.
"""

import random

import pytest

from src.core.types import EntityType

from benchmarks.arms.presidio_custom.engine import PresidioCustomArm
from benchmarks.arms.presidio_stock import PresidioStockArm
from benchmarks.generate.entity_values import generate_value

pytestmark = pytest.mark.real_model

_FIVE_CUSTOM_TYPES: tuple[EntityType, ...] = ("AADHAAR", "PAN", "IFSC", "UPI", "VEHICLE_REG")


@pytest.fixture(scope="module")
def arm() -> PresidioCustomArm:
    return PresidioCustomArm()


def test_custom_arm_detects_each_of_the_five_added_entity_types(arm: PresidioCustomArm) -> None:
    for entity_type in _FIVE_CUSTOM_TYPES:
        value = generate_value(entity_type, random.Random(0))
        text = f"The value on file is {value}, please confirm."
        predictions = arm.predict(text)
        matches = [p for p in predictions if p.entity_type == entity_type]
        assert len(matches) == 1, f"{entity_type} not detected in {text!r}: got {predictions}"
        assert text[matches[0].start : matches[0].end] == value


def test_custom_arm_still_detects_everything_stock_presidio_detects() -> None:
    stock = PresidioStockArm()
    custom = PresidioCustomArm()
    text = "Contact Arjun Reddy at arjun.reddy@example.com or 9876543210."
    stock_predictions = {(p.start, p.end, p.entity_type) for p in stock.predict(text)}
    custom_predictions = {(p.start, p.end, p.entity_type) for p in custom.predict(text)}
    assert stock_predictions.issubset(custom_predictions)


def test_custom_arm_detects_multiple_entity_types_in_one_sentence(arm: PresidioCustomArm) -> None:
    aadhaar = generate_value("AADHAAR", random.Random(1))
    pan = generate_value("PAN", random.Random(2))
    text = f"For KYC purposes, share your Aadhaar {aadhaar} and PAN {pan} with the branch."
    predictions = arm.predict(text)
    found_types = {p.entity_type for p in predictions}
    assert "AADHAAR" in found_types
    assert "PAN" in found_types


def test_custom_arm_predictions_have_valid_offsets_into_the_original_text(
    arm: PresidioCustomArm,
) -> None:
    ifsc = generate_value("IFSC", random.Random(3))
    text = f"The beneficiary bank IFSC code is {ifsc} for the NEFT transfer."
    predictions = arm.predict(text)
    assert len(predictions) > 0
    for prediction in predictions:
        assert 0 <= prediction.start < prediction.end <= len(text)
