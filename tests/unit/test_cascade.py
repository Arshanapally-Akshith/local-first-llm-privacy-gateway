"""detect.cascade.detect(): proves the real registry + precedence are
wired together correctly. registry.py and precedence.py each already
have their own exhaustive unit tests — these only prove the wiring."""

from src.detect.cascade import detect
from src.detect.tier1.checksum import verhoeff_generate_check_digit

_PAYLOAD = "23456789012"
_VALID_AADHAAR = _PAYLOAD + verhoeff_generate_check_digit(_PAYLOAD)
_VALID_PAN = "AAAPL1234C"


def test_empty_text_returns_no_spans() -> None:
    assert detect("") == []


def test_text_with_no_entities_returns_no_spans() -> None:
    assert detect("just an ordinary sentence with no PII in it") == []


def test_finds_a_single_entity() -> None:
    spans = detect(f"my Aadhaar is {_VALID_AADHAAR}")

    assert len(spans) == 1
    assert spans[0].entity_type == "AADHAAR"
    assert spans[0].tier == 1


def test_finds_multiple_non_overlapping_entities_from_different_detectors() -> None:
    text = f"Aadhaar {_VALID_AADHAAR} and PAN {_VALID_PAN}"

    spans = detect(text)

    entity_types = {span.entity_type for span in spans}
    assert entity_types == {"AADHAAR", "PAN"}


def test_a_bad_checksum_is_not_detected() -> None:
    # Same shape as a valid Aadhaar (12 digits) but the last digit is
    # wrong for Verhoeff — must not appear as a detected span at all.
    bad_aadhaar = (
        _PAYLOAD + "0" if verhoeff_generate_check_digit(_PAYLOAD) != "0" else _PAYLOAD + "1"
    )

    assert detect(f"Aadhaar {bad_aadhaar}") == []


def test_returned_spans_are_sorted_by_start_and_non_overlapping() -> None:
    text = f"{_VALID_PAN} then later {_VALID_AADHAAR}"

    spans = detect(text)

    starts = [span.start for span in spans]
    assert starts == sorted(starts)
    for a, b in zip(spans, spans[1:], strict=False):
        assert a.end <= b.start
