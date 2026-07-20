"""UpiDetector: positive, negative, and near-miss cases.

`fakebank` is used as the PSP handle — not a real NPCI-registered
handle (real ones include `okhdfcbank`, `ybl`, `paytm`), kept
obviously synthetic. The email-shaped near-miss is the structurally
important case: it proves the dot-in-domain rule that keeps
`UpiDetector` and `EmailDetector` from double-claiming the same span
(see upi.py's docstring).
"""

from src.core.types import Offset, Span
from src.detect.tier1.upi import UpiDetector

_VALID_UPI = "arjun.reddy@fakebank"
_EMAIL_SHAPED_TOKEN = "arjun.reddy@example.com"


def test_detects_valid_upi_id_embedded_in_text() -> None:
    text = f"pay to {_VALID_UPI} now"
    detector = UpiDetector()

    spans = detector.detect(text)

    expected_start = text.index(_VALID_UPI)
    expected_end = expected_start + len(_VALID_UPI)
    assert spans == [
        Span(start=Offset(expected_start), end=Offset(expected_end), entity_type="UPI", tier=1)
    ]


def test_detects_nothing_in_text_with_no_upi_shaped_token() -> None:
    assert UpiDetector().detect("no sensitive identifiers here at all") == []


def test_rejects_email_shaped_token() -> None:
    text = f"contact {_EMAIL_SHAPED_TOKEN} for support"
    assert UpiDetector().detect(text) == []


def test_rejects_token_with_no_at_sign() -> None:
    assert UpiDetector().detect("just some text without an at sign") == []


def test_detects_two_valid_upi_ids_in_one_text() -> None:
    text = f"first {_VALID_UPI} second {_VALID_UPI}"

    spans = UpiDetector().detect(text)

    assert len(spans) == 2
    assert all(span.entity_type == "UPI" and span.tier == 1 for span in spans)


def test_empty_string_detects_nothing() -> None:
    assert UpiDetector().detect("") == []
