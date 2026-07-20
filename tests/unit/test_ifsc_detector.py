"""IfscDetector: positive, negative, and near-miss cases.

`ABCD0123456` is used as the valid fixture — a 4-letter bank-code
prefix not assigned to any real RBI-registered bank, kept obviously
synthetic per the same reasoning as the Aadhaar/Card fixtures.
"""

from src.core.types import Offset, Span
from src.detect.tier1.ifsc import IfscDetector

_VALID_IFSC = "ABCD0123456"
_BAD_LITERAL_IFSC = "ABCD1123456"  # 5th char '1', not the reserved '0'


def test_detects_valid_ifsc_embedded_in_text() -> None:
    text = f"IFSC: {_VALID_IFSC} for this branch"
    detector = IfscDetector()

    spans = detector.detect(text)

    expected_start = text.index(_VALID_IFSC)
    expected_end = expected_start + len(_VALID_IFSC)
    assert spans == [
        Span(start=Offset(expected_start), end=Offset(expected_end), entity_type="IFSC", tier=1)
    ]


def test_detects_nothing_in_text_with_no_ifsc_shaped_token() -> None:
    assert IfscDetector().detect("no sensitive identifiers here at all") == []


def test_rejects_token_with_non_zero_fifth_character() -> None:
    text = f"IFSC: {_BAD_LITERAL_IFSC} for this branch"
    assert IfscDetector().detect(text) == []


def test_rejects_lowercase_ifsc() -> None:
    assert IfscDetector().detect("ifsc: abcd0123456 for this branch") == []


def test_rejects_wrong_length_token() -> None:
    assert IfscDetector().detect("IFSC: ABCD012345 for this branch") == []


def test_detects_two_valid_ifscs_in_one_text() -> None:
    text = f"first {_VALID_IFSC} second {_VALID_IFSC}"

    spans = IfscDetector().detect(text)

    assert len(spans) == 2
    assert all(span.entity_type == "IFSC" and span.tier == 1 for span in spans)


def test_empty_string_detects_nothing() -> None:
    assert IfscDetector().detect("") == []
