"""PanDetector: positive, negative, and near-miss cases.

`ABCPE1234F` is used as the valid fixture (4th char `P`, a real
Income Tax Department category letter for "Individual"). Note:
`ABCDE1234F` — the PAN-shaped string used throughout this repo since
Phase 0/1 as a generic placeholder (ARCHITECTURE.md, BUILD.md, and
several Phase 0/1 tests) — is *not* structurally valid PAN (4th char
`D` is not a category letter). Those earlier tests never validated
PAN structure, so this was never a bug there; it is used deliberately
below as a real near-miss case instead.
"""

from src.core.types import Offset, Span
from src.detect.tier1.pan import PanDetector

_VALID_PAN = "ABCPE1234F"
_BAD_CATEGORY_PAN = "ABCDE1234F"


def test_detects_valid_pan_embedded_in_text() -> None:
    text = f"PAN on file: {_VALID_PAN} for verification"
    detector = PanDetector()

    spans = detector.detect(text)

    expected_start = text.index(_VALID_PAN)
    expected_end = expected_start + len(_VALID_PAN)
    assert spans == [
        Span(start=Offset(expected_start), end=Offset(expected_end), entity_type="PAN", tier=1)
    ]


def test_detects_nothing_in_text_with_no_pan_shaped_token() -> None:
    assert PanDetector().detect("no sensitive identifiers here at all") == []


def test_rejects_pan_shaped_token_with_invalid_category_letter() -> None:
    text = f"Reference {_BAD_CATEGORY_PAN} for this ticket."
    assert PanDetector().detect(text) == []


def test_rejects_lowercase_pan() -> None:
    assert PanDetector().detect("pan is abcpe1234f here") == []


def test_rejects_wrong_length_token() -> None:
    assert PanDetector().detect("PAN is ABCPE123F here") == []


def test_detects_two_valid_pans_in_one_text() -> None:
    text = f"first {_VALID_PAN} second {_VALID_PAN}"

    spans = PanDetector().detect(text)

    assert len(spans) == 2
    assert all(span.entity_type == "PAN" and span.tier == 1 for span in spans)


def test_empty_string_detects_nothing() -> None:
    assert PanDetector().detect("") == []
