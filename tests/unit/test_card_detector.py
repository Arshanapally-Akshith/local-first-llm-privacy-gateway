"""CardDetector: positive, negative, and near-miss cases (BUILD.md
Phase 2 DoD: "Each entity type has positive + negative + near-miss
tests (bad checksum -> not detected)").

`4111111111111111` is the industry-standard Visa test/sandbox card
number (used across Stripe, PayPal, and virtually every payment
provider's own docs) — never a real, issuable card, so no reserved-
range concern applies the way it does for Aadhaar.
"""

from src.core.types import Offset, Span
from src.detect.tier1.card import CardDetector
from src.detect.tier1.checksum import luhn_generate_check_digit

_VALID_CARD = "4111111111111111"
_BAD_CHECKSUM_CARD = "4111111111111112"


def test_detects_valid_card_embedded_in_text() -> None:
    text = f"Card on file: {_VALID_CARD} exp 12/30"
    detector = CardDetector()

    spans = detector.detect(text)

    expected_start = text.index(_VALID_CARD)
    expected_end = expected_start + len(_VALID_CARD)
    assert spans == [
        Span(
            start=Offset(expected_start),
            end=Offset(expected_end),
            entity_type="CARD",
            tier=1,
        )
    ]


def test_detects_nothing_in_text_with_no_digit_run() -> None:
    detector = CardDetector()

    assert detector.detect("no sensitive numbers here at all") == []


def test_rejects_card_length_run_with_bad_checksum() -> None:
    text = f"Order id {_BAD_CHECKSUM_CARD} was refunded."
    detector = CardDetector()

    assert detector.detect(text) == []


def test_rejects_digit_run_shorter_than_twelve() -> None:
    detector = CardDetector()

    assert detector.detect("short run: 1234567890") == []


def test_detects_shortest_supported_length_thirteen_digit_card() -> None:
    # 13 digits is the shortest length ISO/IEC 7812 card numbers use in
    # practice (some legacy Visa cards); the candidate pattern's lower
    # bound is 12 to match BUILD.md's "12-to-19 digit" framing, but the
    # detector must still gate purely on Luhn validity, not length.
    # Derived (not guessed) so the fixture is provably Luhn-valid: the
    # last digit is computed from the other twelve.
    payload = "411111111111"
    valid_13 = payload + luhn_generate_check_digit(payload)
    detector = CardDetector()

    spans = detector.detect(f"card {valid_13} used")

    assert len(spans) == 1
    assert spans[0].entity_type == "CARD"


def test_detects_two_valid_cards_in_one_text() -> None:
    detector = CardDetector()
    text = f"first {_VALID_CARD} second {_VALID_CARD}"

    spans = detector.detect(text)

    assert len(spans) == 2
    assert all(span.entity_type == "CARD" and span.tier == 1 for span in spans)


def test_empty_string_detects_nothing() -> None:
    assert CardDetector().detect("") == []
