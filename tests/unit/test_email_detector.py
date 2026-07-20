"""EmailDetector: positive, negative, and near-miss cases.

`example.com` is RFC 2606's reserved documentation domain — the
standard, correct choice for a synthetic test fixture. The UPI-shaped
near-miss proves the same non-collision boundary from the other side
(see test_upi_detector.py and upi.py's docstring).
"""

from src.core.types import Offset, Span
from src.detect.tier1.email import EmailDetector

_VALID_EMAIL = "arjun.reddy@example.com"
_UPI_SHAPED_TOKEN = "arjun.reddy@fakebank"


def test_detects_valid_email_embedded_in_text() -> None:
    text = f"contact {_VALID_EMAIL} for support"
    detector = EmailDetector()

    spans = detector.detect(text)

    expected_start = text.index(_VALID_EMAIL)
    expected_end = expected_start + len(_VALID_EMAIL)
    assert spans == [
        Span(start=Offset(expected_start), end=Offset(expected_end), entity_type="EMAIL", tier=1)
    ]


def test_detects_nothing_in_text_with_no_email_shaped_token() -> None:
    assert EmailDetector().detect("no sensitive identifiers here at all") == []


def test_rejects_upi_shaped_token_with_no_dotted_domain() -> None:
    text = f"pay to {_UPI_SHAPED_TOKEN} now"
    assert EmailDetector().detect(text) == []


def test_rejects_token_with_no_at_sign() -> None:
    assert EmailDetector().detect("just some text without an at sign") == []


def test_rejects_token_with_single_letter_tld() -> None:
    assert EmailDetector().detect("contact arjun.reddy@example.c for support") == []


def test_detects_two_valid_emails_in_one_text() -> None:
    text = f"first {_VALID_EMAIL} second {_VALID_EMAIL}"

    spans = EmailDetector().detect(text)

    assert len(spans) == 2
    assert all(span.entity_type == "EMAIL" and span.tier == 1 for span in spans)


def test_empty_string_detects_nothing() -> None:
    assert EmailDetector().detect("") == []
