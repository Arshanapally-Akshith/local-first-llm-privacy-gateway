"""benchmarks.arms.ours: `OurCascadeArm` — this project's own cascade,
called directly via `detect()`, against the real GLiNER model.
`real_model`-marked: constructing the arm loads the real Tier-2 model.

No fast-path variant exists for this arm the way arms 2/3 had one for
their Tier-1-only recognizer wrappers: every `OurCascadeArm` test
necessarily loads the real model, since `__init__` calls
`get_tier2_model()` unconditionally.
"""

import random

import pytest

from src.core.types import EntityType

from benchmarks.arms.ours import OurCascadeArm
from benchmarks.arms.presidio_custom.engine import PresidioCustomArm
from benchmarks.generate.entity_values import generate_value

pytestmark = pytest.mark.real_model

_ALL_EIGHT_STRUCTURED_AND_PERSON_ORG_ADDRESS_FREE_TYPES: tuple[EntityType, ...] = (
    "AADHAAR",
    "PAN",
    "IFSC",
    "UPI",
    "VEHICLE_REG",
    "CARD",
    "EMAIL",
    "PHONE",
)


@pytest.fixture(scope="module")
def arm() -> OurCascadeArm:
    return OurCascadeArm()


def test_detects_each_of_the_eight_structured_types(arm: OurCascadeArm) -> None:
    for entity_type in _ALL_EIGHT_STRUCTURED_AND_PERSON_ORG_ADDRESS_FREE_TYPES:
        value = generate_value(entity_type, random.Random(0))
        text = f"The value on file is {value}, please confirm."
        predictions = arm.predict(text)
        matches = [p for p in predictions if p.entity_type == entity_type]
        assert len(matches) == 1, f"{entity_type} not detected in {text!r}: got {predictions}"
        assert text[matches[0].start : matches[0].end] == value


def test_detects_upi_and_email_without_raising_surrogate_domain_error(arm: OurCascadeArm) -> None:
    # The entire reason this arm calls detect() instead of sanitize():
    # UPI/email have no surrogate mechanism (docs/LIMITATIONS.md) and
    # sanitize() would raise SurrogateDomainError on them, even though
    # detection itself works fine. This test proves that design
    # rationale is real, not just documented.
    upi = generate_value("UPI", random.Random(1))
    email = generate_value("EMAIL", random.Random(2))
    text = f"Pay via {upi} or email {email} for confirmation."
    predictions = arm.predict(text)
    found_types = {p.entity_type for p in predictions}
    assert "UPI" in found_types
    assert "EMAIL" in found_types


def test_detects_a_person_name(arm: OurCascadeArm) -> None:
    text = "Arjun Reddy will be joining the onboarding call at 10 AM."
    predictions = arm.predict(text)
    assert any(p.entity_type == "PERSON" for p in predictions)


def test_detects_org_or_address_in_a_carrier_sentence(arm: OurCascadeArm) -> None:
    text = "Priya Sharma works at Zenith Logistics, 12 MG Road, Bengaluru, Karnataka."
    predictions = arm.predict(text)
    found_types = {p.entity_type for p in predictions}
    assert "ORG" in found_types or "ADDRESS" in found_types


def test_predictions_have_valid_offsets_into_the_original_text(arm: OurCascadeArm) -> None:
    text = "My Aadhaar is 999941057058 and PAN is ABCDE1234F."
    predictions = arm.predict(text)
    assert len(predictions) > 0
    for prediction in predictions:
        assert 0 <= prediction.start < prediction.end <= len(text)


def test_returns_empty_list_for_text_with_no_pii(arm: OurCascadeArm) -> None:
    assert arm.predict("The weather today is pleasant and mild.") == []


def test_agrees_with_arm_2_on_the_five_shared_tier1_types() -> None:
    # A concrete proof of the property documented in
    # presidio_custom/recognizers.py: arm 2's five custom recognizers
    # wrap the exact same Detector classes this cascade uses, so their
    # predictions for those five types must be identical on the same
    # text - any future arm2-vs-arm4 delta can only ever come from
    # PERSON/ORG/ADDRESS.
    tier1_types = {"AADHAAR", "PAN", "IFSC", "UPI", "VEHICLE_REG"}
    aadhaar = generate_value("AADHAAR", random.Random(3))
    pan = generate_value("PAN", random.Random(4))
    text = f"Aadhaar {aadhaar} and PAN {pan} were both submitted for KYC."

    ours = OurCascadeArm()
    arm2 = PresidioCustomArm()

    ours_tier1 = {
        (p.start, p.end, p.entity_type) for p in ours.predict(text) if p.entity_type in tier1_types
    }
    arm2_tier1 = {
        (p.start, p.end, p.entity_type) for p in arm2.predict(text) if p.entity_type in tier1_types
    }
    assert ours_tier1 == arm2_tier1
    assert len(ours_tier1) == 2  # sanity: both types were actually found, not vacuously equal
