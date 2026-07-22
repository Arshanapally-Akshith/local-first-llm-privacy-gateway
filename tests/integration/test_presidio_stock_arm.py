"""benchmarks.arms.presidio_stock: `PresidioStockArm` against the real,
installed `en_core_web_lg`-backed `AnalyzerEngine` — `real_model`-marked
(network on first run to resolve the model, heavy CPU/RAM always),
mirroring `tests/integration/test_tier2_real_model.py`'s own precedent
for this project's other real-model-dependent suite.

Assertions here were written after observing real `AnalyzerEngine`
output for these exact sentences (a throwaway probe, not committed),
the same "measure, don't guess" discipline
`docs/DECISIONS.md`'s Phase 4 Task 2 entry already established for this
project's own Tier-2 model evaluation.
"""

import pytest

from benchmarks.arms.presidio_stock import PresidioStockArm

pytestmark = pytest.mark.real_model


@pytest.fixture(scope="module")
def arm() -> PresidioStockArm:
    return PresidioStockArm()


def test_stock_arm_detects_a_credit_card_number(arm: PresidioStockArm) -> None:
    text = "My card number 4111111111111111 was declined at checkout."
    predictions = arm.predict(text)
    card_predictions = [p for p in predictions if p.entity_type == "CARD"]
    assert len(card_predictions) == 1
    assert text[card_predictions[0].start : card_predictions[0].end] == "4111111111111111"


def test_stock_arm_detects_an_email_address(arm: PresidioStockArm) -> None:
    text = "Send the invoice to jane.doe@example.com by end of day."
    predictions = arm.predict(text)
    email_predictions = [p for p in predictions if p.entity_type == "EMAIL"]
    assert len(email_predictions) == 1
    assert text[email_predictions[0].start : email_predictions[0].end] == "jane.doe@example.com"


def test_stock_arm_detects_a_person_name(arm: PresidioStockArm) -> None:
    text = "Arjun Reddy will be joining the onboarding call at 10 AM."
    predictions = arm.predict(text)
    person_predictions = [p for p in predictions if p.entity_type == "PERSON"]
    assert len(person_predictions) >= 1


def test_stock_arm_never_predicts_aadhaar_or_pan_or_ifsc_or_upi_or_vehicle_reg(
    arm: PresidioStockArm,
) -> None:
    # The entire fairness point of arm 2: stock Presidio has no
    # recognizer for any of these five, so a fully vanilla engine must
    # never emit them, regardless of what appears in the text.
    text = (
        "Aadhaar 999941057058, PAN ABCDE1234F, IFSC HDFC0001234, "
        "UPI ravi@oksbi, vehicle KA01AB1234."
    )
    predictions = arm.predict(text)
    forbidden = {"AADHAAR", "PAN", "IFSC", "UPI", "VEHICLE_REG"}
    assert not any(p.entity_type in forbidden for p in predictions)


def test_stock_arm_returns_no_predictions_for_text_with_no_pii(arm: PresidioStockArm) -> None:
    assert arm.predict("The weather today is pleasant and mild.") == []


def test_stock_arm_predictions_have_valid_offsets_into_the_original_text(
    arm: PresidioStockArm,
) -> None:
    text = "Contact Priya Sharma at priya.sharma@example.org or 9876543210."
    predictions = arm.predict(text)
    assert len(predictions) > 0
    for prediction in predictions:
        assert 0 <= prediction.start < prediction.end <= len(text)
