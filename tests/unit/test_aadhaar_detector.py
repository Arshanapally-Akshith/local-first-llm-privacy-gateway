"""AadhaarDetector: positive, negative, and near-miss cases (BUILD.md
Phase 2 DoD: "Each entity type has positive + negative + near-miss
tests (bad checksum -> not detected)").

`234567890124` is a Verhoeff-valid 12-digit string used here purely as
an algorithmic test vector (verified in test_checksum.py against
Verhoeff's own construction). It has *not* been checked against
UIDAI's documented never-issued reserved ranges — that verification is
Phase 2 Task 5's responsibility (the FF1 surrogate/reserved-range
generator), which is the component that actually publishes Aadhaar-
shaped values as a committed artifact. A single literal used only
inside an assertion in this test module is not that.
"""

from src.core.types import Offset, Span
from src.detect.tier1.aadhaar import AadhaarDetector

_VALID_AADHAAR = "234567890124"
_BAD_CHECKSUM_AADHAAR = "234567890125"


def test_detects_valid_aadhaar_embedded_in_text() -> None:
    text = f"My Aadhaar number is {_VALID_AADHAAR}, please verify."
    detector = AadhaarDetector()

    spans = detector.detect(text)

    expected_start = text.index(_VALID_AADHAAR)
    expected_end = expected_start + len(_VALID_AADHAAR)
    assert spans == [
        Span(
            start=Offset(expected_start),
            end=Offset(expected_end),
            entity_type="AADHAAR",
            tier=1,
        )
    ]


def test_detects_nothing_in_text_with_no_digit_run() -> None:
    detector = AadhaarDetector()

    assert detector.detect("no sensitive numbers here at all") == []


def test_rejects_twelve_digit_run_with_bad_checksum() -> None:
    text = f"Reference number {_BAD_CHECKSUM_AADHAAR} for this ticket."
    detector = AadhaarDetector()

    assert detector.detect(text) == []


def test_rejects_eleven_digit_run() -> None:
    detector = AadhaarDetector()

    assert detector.detect("phone-ish run: 23456789012") == []


def test_rejects_thirteen_digit_run() -> None:
    # A 13-digit run does not word-boundary-isolate into a 12-digit
    # candidate anywhere within it, by design (see aadhaar.py).
    detector = AadhaarDetector()

    assert detector.detect(f"{_VALID_AADHAAR}9") == []


def test_detects_two_valid_aadhaars_in_one_text() -> None:
    detector = AadhaarDetector()
    text = f"first {_VALID_AADHAAR} second {_VALID_AADHAAR}"

    spans = detector.detect(text)

    assert len(spans) == 2
    assert all(span.entity_type == "AADHAAR" and span.tier == 1 for span in spans)


def test_empty_string_detects_nothing() -> None:
    assert AadhaarDetector().detect("") == []
