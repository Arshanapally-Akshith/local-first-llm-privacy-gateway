"""benchmarks.arms.presidio_gliner: `PresidioGlinerArm` against the
real, installed GLiNER model (`gliner_multi_pii-v1`, the same weights
`src/detect/tier2/gliner_model.py::get_tier2_model()` warms for the live
gateway) and the real `AnalyzerEngine` with `SpacyRecognizer` removed.
`real_model`-marked: loads two real models (spaCy for tokenization/other
stock recognizers' NLP artifacts, GLiNER for PERSON/ORG/ADDRESS), so
this is the heaviest test module in the benchmark suite.
"""

import random

import pytest

from src.core.types import EntityType

from benchmarks.arms.presidio_gliner.engine import PresidioGlinerArm
from benchmarks.generate.entity_values import generate_value

pytestmark = pytest.mark.real_model

_FIVE_CUSTOM_TYPES: tuple[EntityType, ...] = ("AADHAAR", "PAN", "IFSC", "UPI", "VEHICLE_REG")


@pytest.fixture(scope="module")
def arm() -> PresidioGlinerArm:
    return PresidioGlinerArm()


def test_gliner_arm_detects_each_of_the_five_tier1_custom_types(arm: PresidioGlinerArm) -> None:
    # Unchanged from arm 2 - the backend swap only affects PERSON/ORG/
    # ADDRESS, never the five Tier-1 custom recognizers.
    for entity_type in _FIVE_CUSTOM_TYPES:
        value = generate_value(entity_type, random.Random(0))
        text = f"The value on file is {value}, please confirm."
        predictions = arm.predict(text)
        matches = [p for p in predictions if p.entity_type == entity_type]
        assert len(matches) == 1, f"{entity_type} not detected in {text!r}: got {predictions}"
        assert text[matches[0].start : matches[0].end] == value


def test_gliner_arm_detects_a_person_name(arm: PresidioGlinerArm) -> None:
    text = "Arjun Reddy will be joining the onboarding call at 10 AM."
    predictions = arm.predict(text)
    person_predictions = [p for p in predictions if p.entity_type == "PERSON"]
    assert len(person_predictions) >= 1


def test_gliner_arm_detects_still_detects_stock_card_email_phone(arm: PresidioGlinerArm) -> None:
    # Confirms the swap only removed SpacyRecognizer - CreditCard/Email/
    # Phone recognizers (never NLP-based) are untouched.
    text = "My card 4111111111111111, email jane.doe@example.com, phone 9876543210."
    predictions = arm.predict(text)
    found_types = {p.entity_type for p in predictions}
    assert {"CARD", "EMAIL", "PHONE"}.issubset(found_types)


def test_gliner_arm_can_detect_org_and_address_which_arm_2_never_could(
    arm: PresidioGlinerArm,
) -> None:
    # This is the entire point of arm 3: ORG/ADDRESS had no source at
    # all in arm 1 or arm 2 (see docs/DECISIONS.md, Phase 5 Task 4,
    # decision point 5). At least one of the two must now be detected
    # somewhere in a sentence carrying both - GLiNER's own measured
    # weakness on some carrier phrasings (Phase 4 Task 2) means neither
    # is individually guaranteed on any single sentence, so this test
    # asserts the capability exists at all, not 100% recall on one
    # example.
    text = "Priya Sharma works at Zenith Logistics, 12 MG Road, Bengaluru, Karnataka."
    predictions = arm.predict(text)
    found_types = {p.entity_type for p in predictions}
    assert "ORG" in found_types or "ADDRESS" in found_types


def test_gliner_arm_predictions_have_valid_offsets_into_the_original_text(
    arm: PresidioGlinerArm,
) -> None:
    text = "Arjun Reddy works at Infosys in Bengaluru."
    predictions = arm.predict(text)
    assert len(predictions) > 0
    for prediction in predictions:
        assert 0 <= prediction.start < prediction.end <= len(text)


def test_gliner_arm_never_predicts_person_via_the_removed_spacy_recognizer(
    arm: PresidioGlinerArm,
) -> None:
    # A name GLiNER is known to miss (Phase 4 Task 2: weak on some
    # Hinglish/transliterated forms) must not be silently caught by a
    # leftover SpacyRecognizer - if SpacyRecognizer were still
    # registered, this would be a false pass masking an incomplete
    # backend swap. Asserting on the underlying registry directly is
    # the precise way to prove removal, independent of any one
    # sentence's detectability.
    # getattr(), not `r.name` directly: Presidio's own type stubs leave
    # EntityRecognizer.name's declared type unresolvable to mypy here.
    recognizer_names = {getattr(r, "name") for r in arm._engine.registry.recognizers}  # noqa: B009
    assert "SpacyRecognizer" not in recognizer_names
