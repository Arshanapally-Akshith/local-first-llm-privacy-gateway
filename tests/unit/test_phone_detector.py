"""PhoneDetector: positive, negative, and near-miss cases, covering the
bare, `+91`-prefixed, `91`-prefixed, and `0`-prefixed canonical forms.
"""

from src.core.types import Offset, Span
from src.detect.tier1.phone import PhoneDetector

_BARE_NUMBER = "9876543210"
_PLUS91_NUMBER = "+919876543210"
_NO_PLUS_91_NUMBER = "919876543210"
_ZERO_PREFIXED_NUMBER = "09876543210"
_BAD_LEADING_DIGIT_NUMBER = "5876543210"


def test_detects_bare_ten_digit_mobile_number() -> None:
    text = f"call {_BARE_NUMBER} now"
    detector = PhoneDetector()

    spans = detector.detect(text)

    expected_start = text.index(_BARE_NUMBER)
    expected_end = expected_start + len(_BARE_NUMBER)
    assert spans == [
        Span(start=Offset(expected_start), end=Offset(expected_end), entity_type="PHONE", tier=1)
    ]


def test_detects_plus_91_prefixed_number() -> None:
    text = f"call {_PLUS91_NUMBER} now"
    spans = PhoneDetector().detect(text)

    expected_start = text.index(_PLUS91_NUMBER)
    expected_end = expected_start + len(_PLUS91_NUMBER)
    assert spans == [
        Span(start=Offset(expected_start), end=Offset(expected_end), entity_type="PHONE", tier=1)
    ]


def test_detects_91_prefixed_number_without_plus() -> None:
    text = f"call {_NO_PLUS_91_NUMBER} now"
    spans = PhoneDetector().detect(text)

    expected_start = text.index(_NO_PLUS_91_NUMBER)
    expected_end = expected_start + len(_NO_PLUS_91_NUMBER)
    assert spans == [
        Span(start=Offset(expected_start), end=Offset(expected_end), entity_type="PHONE", tier=1)
    ]


def test_detects_zero_prefixed_number() -> None:
    text = f"call {_ZERO_PREFIXED_NUMBER} now"
    spans = PhoneDetector().detect(text)

    expected_start = text.index(_ZERO_PREFIXED_NUMBER)
    expected_end = expected_start + len(_ZERO_PREFIXED_NUMBER)
    assert spans == [
        Span(start=Offset(expected_start), end=Offset(expected_end), entity_type="PHONE", tier=1)
    ]


def test_still_detects_bare_number_starting_with_nine_one() -> None:
    # "9123456789" is a legitimate bare 10-digit number whose first two
    # digits happen to look like the "91" country-code prefix. The
    # detector must not misparse it as a truncated 8-digit-body match.
    number = "9123456789"
    spans = PhoneDetector().detect(f"call {number} now")

    assert len(spans) == 1
    assert spans[0].entity_type == "PHONE"


def test_detects_nothing_in_text_with_no_digit_run() -> None:
    assert PhoneDetector().detect("no sensitive numbers here at all") == []


def test_rejects_leading_digit_outside_six_to_nine() -> None:
    text = f"call {_BAD_LEADING_DIGIT_NUMBER} now"
    assert PhoneDetector().detect(text) == []


def test_rejects_number_glued_directly_to_a_letter() -> None:
    assert PhoneDetector().detect("callme9876543210 now") == []


def test_rejects_nine_digit_run() -> None:
    assert PhoneDetector().detect("call 987654321 now") == []


def test_detects_two_valid_numbers_in_one_text() -> None:
    text = f"first {_BARE_NUMBER} second {_BARE_NUMBER}"

    spans = PhoneDetector().detect(text)

    assert len(spans) == 2
    assert all(span.entity_type == "PHONE" and span.tier == 1 for span in spans)


def test_empty_string_detects_nothing() -> None:
    assert PhoneDetector().detect("") == []
