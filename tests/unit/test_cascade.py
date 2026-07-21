"""detect.cascade.detect(): proves the real registry + precedence are
wired together correctly, and (Phase 3 Task 3) that ingress-surrogate
recognition against a session's known-surrogate registry is applied as
the final step. registry.py and precedence.py each already have their
own exhaustive unit tests — those aspects here only prove the wiring.
"""

from datetime import datetime, timezone

from src.core.types import SessionId
from src.detect.cascade import detect
from src.detect.tier1.checksum import verhoeff_generate_check_digit
from src.session.session import Session

_PAYLOAD = "23456789012"
_VALID_AADHAAR = _PAYLOAD + verhoeff_generate_check_digit(_PAYLOAD)
_VALID_PAN = "AAAPL1234C"
_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _fresh_session() -> Session:
    return Session(SessionId("s1"), created_at=_NOW)


def test_empty_text_returns_no_spans() -> None:
    assert detect("", _fresh_session()) == []


def test_text_with_no_entities_returns_no_spans() -> None:
    assert detect("just an ordinary sentence with no PII in it", _fresh_session()) == []


def test_finds_a_single_entity() -> None:
    resolved = detect(f"my Aadhaar is {_VALID_AADHAAR}", _fresh_session())

    assert len(resolved) == 1
    assert resolved[0].span.entity_type == "AADHAAR"
    assert resolved[0].span.tier == 1


def test_finds_multiple_non_overlapping_entities_from_different_detectors() -> None:
    text = f"Aadhaar {_VALID_AADHAAR} and PAN {_VALID_PAN}"

    resolved = detect(text, _fresh_session())

    entity_types = {r.span.entity_type for r in resolved}
    assert entity_types == {"AADHAAR", "PAN"}


def test_a_bad_checksum_is_not_detected() -> None:
    # Same shape as a valid Aadhaar (12 digits) but the last digit is
    # wrong for Verhoeff — must not appear as a detected span at all.
    bad_aadhaar = (
        _PAYLOAD + "0" if verhoeff_generate_check_digit(_PAYLOAD) != "0" else _PAYLOAD + "1"
    )

    assert detect(f"Aadhaar {bad_aadhaar}", _fresh_session()) == []


def test_returned_spans_are_sorted_by_start_and_non_overlapping() -> None:
    text = f"{_VALID_PAN} then later {_VALID_AADHAAR}"

    resolved = detect(text, _fresh_session())

    starts = [r.span.start for r in resolved]
    assert starts == sorted(starts)
    for a, b in zip(resolved, resolved[1:], strict=False):
        assert a.span.end <= b.span.start


def test_a_value_with_no_session_history_is_not_an_ingress_surrogate() -> None:
    resolved = detect(f"Aadhaar {_VALID_AADHAAR}", _fresh_session())

    assert resolved[0].is_ingress_surrogate is False


def test_a_known_surrogate_is_recognised_as_an_ingress_surrogate() -> None:
    session = _fresh_session()
    session.record_surrogate(_VALID_AADHAAR, "AADHAAR", _NOW)

    resolved = detect(f"Noted: {_VALID_AADHAAR}", session)

    assert len(resolved) == 1
    assert resolved[0].is_ingress_surrogate is True


def test_recognition_is_per_session_not_global() -> None:
    """The exact same value is a known surrogate in one session and a
    brand-new real value in another — recognition must not leak across
    sessions."""
    session_with_history = _fresh_session()
    session_with_history.record_surrogate(_VALID_AADHAAR, "AADHAAR", _NOW)
    fresh_session = Session(SessionId("s2"), created_at=_NOW)

    recognised = detect(f"Noted: {_VALID_AADHAAR}", session_with_history)
    unrecognised = detect(f"Noted: {_VALID_AADHAAR}", fresh_session)

    assert recognised[0].is_ingress_surrogate is True
    assert unrecognised[0].is_ingress_surrogate is False


def test_recognition_does_not_affect_which_spans_are_resolved() -> None:
    """A known surrogate alongside a genuinely new entity: precedence
    resolution and span boundaries are unaffected by recognition — only
    the `is_ingress_surrogate` flag differs between the two."""
    session = _fresh_session()
    session.record_surrogate(_VALID_AADHAAR, "AADHAAR", _NOW)
    text = f"Known: {_VALID_AADHAAR}, new PAN: {_VALID_PAN}"

    resolved = detect(text, session)

    by_type = {r.span.entity_type: r for r in resolved}
    assert by_type["AADHAAR"].is_ingress_surrogate is True
    assert by_type["PAN"].is_ingress_surrogate is False
