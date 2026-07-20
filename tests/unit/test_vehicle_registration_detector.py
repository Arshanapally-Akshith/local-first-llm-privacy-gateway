"""VehicleRegistrationDetector: positive, negative, and near-miss
cases, covering both the state-code and BH-series schemes.

State codes used (`KA`, `DL`) are the two most commonly cited generic
illustrative prefixes in Indian documentation/tutorials, not tied to
any specific real vehicle — plate patterns alone, without a real
registry lookup, are not identifying.
"""

from src.core.types import Offset, Span
from src.detect.tier1.vehicle_registration import VehicleRegistrationDetector

_VALID_STATE_CODE_PLATE = "KA01AB1234"
_VALID_SHORT_RTO_PLATE = "DL8CAF5678"  # 1-digit RTO, 3-letter series
_VALID_BH_SERIES_PLATE = "23BH1234AB"
_FOUR_LETTER_SERIES_NEAR_MISS = "KA01ABCD1234"  # series too long for either scheme


def test_detects_valid_state_code_plate_embedded_in_text() -> None:
    text = f"car {_VALID_STATE_CODE_PLATE} parked outside"
    detector = VehicleRegistrationDetector()

    spans = detector.detect(text)

    expected_start = text.index(_VALID_STATE_CODE_PLATE)
    expected_end = expected_start + len(_VALID_STATE_CODE_PLATE)
    assert spans == [
        Span(
            start=Offset(expected_start),
            end=Offset(expected_end),
            entity_type="VEHICLE_REG",
            tier=1,
        )
    ]


def test_detects_valid_short_rto_three_letter_series_plate() -> None:
    spans = VehicleRegistrationDetector().detect(f"car {_VALID_SHORT_RTO_PLATE} parked")

    assert len(spans) == 1
    assert spans[0].entity_type == "VEHICLE_REG"


def test_detects_valid_bh_series_plate() -> None:
    spans = VehicleRegistrationDetector().detect(f"car {_VALID_BH_SERIES_PLATE} parked")

    assert len(spans) == 1
    assert spans[0].entity_type == "VEHICLE_REG"


def test_detects_nothing_in_text_with_no_plate_shaped_token() -> None:
    assert VehicleRegistrationDetector().detect("no sensitive identifiers here at all") == []


def test_rejects_four_letter_series_matching_neither_scheme() -> None:
    text = f"car {_FOUR_LETTER_SERIES_NEAR_MISS} parked"
    assert VehicleRegistrationDetector().detect(text) == []


def test_rejects_lowercase_plate() -> None:
    assert VehicleRegistrationDetector().detect("car ka01ab1234 parked") == []


def test_detects_two_valid_plates_in_one_text() -> None:
    text = f"first {_VALID_STATE_CODE_PLATE} second {_VALID_BH_SERIES_PLATE}"

    spans = VehicleRegistrationDetector().detect(text)

    assert len(spans) == 2
    assert all(span.entity_type == "VEHICLE_REG" and span.tier == 1 for span in spans)


def test_empty_string_detects_nothing() -> None:
    assert VehicleRegistrationDetector().detect("") == []
