"""detect.cascade.detect(): proves the real registry + precedence are
wired together correctly, and (Phase 3 Task 3) that ingress-surrogate
recognition against a session's known-surrogate registry is applied as
the final step. registry.py and precedence.py each already have their
own exhaustive unit tests — those aspects here only prove the wiring.

Phase 4 Task 3 adds Tier-2 into the same wiring, against a fake
`Tier2Model` (real-model behaviour is exercised separately, under the
`real_model` marker — see `tests/integration/test_tier2_real_model.py`).
`_NO_FINDINGS_MODEL` is used for every pre-existing Tier-1-only test so
their assertions stay about Tier-1 behaviour specifically, unaffected by
Tier-2 now always running too.

Phase 4 Task 4 adds `FAIL_MODE` gating around the Tier-2 stage — see the
tests under "Tier-2 failures are gated by FAIL_MODE" below. `_detect()`
is a thin wrapper supplying a fixed `fail_mode`/`correlation_id` for
every test that doesn't care about them, so the bulk of this file reads
exactly as it did before Task 4.
"""

import json
import logging
from datetime import datetime, timezone

import pytest

from src.core.fail_mode import FailClosedError, FailMode
from src.core.logging import PiiSafeFormatter
from src.core.types import CorrelationId, EntityType, Offset, SessionId
from src.detect.cascade import ResolvedSpan, detect
from src.detect.tier1.checksum import verhoeff_generate_check_digit
from src.detect.tier2.model import ModelEntityMatch, Tier2Model
from src.session.session import Session

_PAYLOAD = "23456789012"
_VALID_AADHAAR = _PAYLOAD + verhoeff_generate_check_digit(_PAYLOAD)
_VALID_PAN = "AAAPL1234C" 
_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
_CORRELATION_ID = CorrelationId("corr-cascade-test")


class _FakeTier2Model:
    """Same fake used in `test_tier2_detector.py` — returns a fixed set
    of matches regardless of `text`."""

    def __init__(self, matches: list[ModelEntityMatch] | None = None) -> None:
        self._matches = matches if matches is not None else []

    def find_entities(self, text: str) -> list[ModelEntityMatch]:
        return self._matches


class _RaisingTier2Model:
    """A `Tier2Model` whose `find_entities()` always raises — a stand-in
    for "the model call itself failed" (ARCHITECTURE.md: "Model
    unavailable → FAIL_MODE"), as opposed to `_FakeTier2Model` returning
    a bad offset (which raises `DetectionError` one layer up, inside
    `Tier2Detector.detect()` — also exercised below, via a real
    out-of-bounds match rather than this class)."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def find_entities(self, text: str) -> list[ModelEntityMatch]:
        raise self._exc


def _match(start: int, end: int, entity_type: EntityType) -> ModelEntityMatch:
    return ModelEntityMatch(start=Offset(start), end=Offset(end), entity_type=entity_type)


_NO_FINDINGS_MODEL: Tier2Model = _FakeTier2Model()


def _fresh_session() -> Session:
    return Session(SessionId("s1"), created_at=_NOW)


def _detect(
    text: str,
    session: Session,
    model: Tier2Model,
    fail_mode: FailMode = "closed",
) -> list[ResolvedSpan]:
    """`detect()`, with a fixed `fail_mode`/`correlation_id` for every
    test that isn't specifically exercising `FAIL_MODE` gating."""
    return detect(text, session, model, fail_mode, correlation_id=_CORRELATION_ID)


def test_empty_text_returns_no_spans() -> None:
    assert _detect("", _fresh_session(), _NO_FINDINGS_MODEL) == []


def test_text_with_no_entities_returns_no_spans() -> None:
    assert (
        _detect("just an ordinary sentence with no PII in it", _fresh_session(), _NO_FINDINGS_MODEL)
        == []
    )


def test_finds_a_single_entity() -> None:
    resolved = _detect(f"my Aadhaar is {_VALID_AADHAAR}", _fresh_session(), _NO_FINDINGS_MODEL)

    assert len(resolved) == 1
    assert resolved[0].span.entity_type == "AADHAAR"
    assert resolved[0].span.tier == 1


def test_finds_multiple_non_overlapping_entities_from_different_detectors() -> None:
    text = f"Aadhaar {_VALID_AADHAAR} and PAN {_VALID_PAN}"

    resolved = _detect(text, _fresh_session(), _NO_FINDINGS_MODEL)

    entity_types = {r.span.entity_type for r in resolved}
    assert entity_types == {"AADHAAR", "PAN"}


def test_a_bad_checksum_is_not_detected() -> None:
    # Same shape as a valid Aadhaar (12 digits) but the last digit is
    # wrong for Verhoeff — must not appear as a detected span at all.
    bad_aadhaar = (
        _PAYLOAD + "0" if verhoeff_generate_check_digit(_PAYLOAD) != "0" else _PAYLOAD + "1"
    )

    assert _detect(f"Aadhaar {bad_aadhaar}", _fresh_session(), _NO_FINDINGS_MODEL) == []


def test_returned_spans_are_sorted_by_start_and_non_overlapping() -> None:
    text = f"{_VALID_PAN} then later {_VALID_AADHAAR}"

    resolved = _detect(text, _fresh_session(), _NO_FINDINGS_MODEL)

    starts = [r.span.start for r in resolved]
    assert starts == sorted(starts)
    for a, b in zip(resolved, resolved[1:], strict=False):
        assert a.span.end <= b.span.start


def test_a_value_with_no_session_history_is_not_an_ingress_surrogate() -> None:
    resolved = _detect(f"Aadhaar {_VALID_AADHAAR}", _fresh_session(), _NO_FINDINGS_MODEL)

    assert resolved[0].is_ingress_surrogate is False


def test_a_known_surrogate_is_recognised_as_an_ingress_surrogate() -> None:
    session = _fresh_session()
    session.record_surrogate(_VALID_AADHAAR, "AADHAAR", _NOW)

    resolved = _detect(f"Noted: {_VALID_AADHAAR}", session, _NO_FINDINGS_MODEL)

    assert len(resolved) == 1
    assert resolved[0].is_ingress_surrogate is True


def test_recognition_is_per_session_not_global() -> None:
    """The exact same value is a known surrogate in one session and a
    brand-new real value in another — recognition must not leak across
    sessions."""
    session_with_history = _fresh_session()
    session_with_history.record_surrogate(_VALID_AADHAAR, "AADHAAR", _NOW)
    fresh_session = Session(SessionId("s2"), created_at=_NOW)

    recognised = _detect(f"Noted: {_VALID_AADHAAR}", session_with_history, _NO_FINDINGS_MODEL)
    unrecognised = _detect(f"Noted: {_VALID_AADHAAR}", fresh_session, _NO_FINDINGS_MODEL)

    assert recognised[0].is_ingress_surrogate is True
    assert unrecognised[0].is_ingress_surrogate is False


def test_recognition_does_not_affect_which_spans_are_resolved() -> None:
    """A known surrogate alongside a genuinely new entity: precedence
    resolution and span boundaries are unaffected by recognition — only
    the `is_ingress_surrogate` flag differs between the two."""
    session = _fresh_session()
    session.record_surrogate(_VALID_AADHAAR, "AADHAAR", _NOW)
    text = f"Known: {_VALID_AADHAAR}, new PAN: {_VALID_PAN}"

    resolved = _detect(text, session, _NO_FINDINGS_MODEL)

    by_type = {r.span.entity_type: r for r in resolved}
    assert by_type["AADHAAR"].is_ingress_surrogate is True
    assert by_type["PAN"].is_ingress_surrogate is False


# --- Phase 4 Task 3: Tier-2 wired into the same cascade ---------------------


def test_tier2_only_finds_a_person_span_with_no_tier1_overlap() -> None:
    text = "Ramesh Kumar called yesterday"
    model = _FakeTier2Model([_match(0, 12, "PERSON")])

    resolved = _detect(text, _fresh_session(), model)

    assert len(resolved) == 1
    assert resolved[0].span.entity_type == "PERSON"
    assert resolved[0].span.tier == 2
    assert resolved[0].is_ingress_surrogate is False


def test_tier1_and_tier2_findings_in_the_same_text_both_survive_when_disjoint() -> None:
    text = f"Ramesh Kumar's PAN is {_VALID_PAN}"
    person_start = text.index("Ramesh")
    person_end = person_start + len("Ramesh Kumar")
    model = _FakeTier2Model([_match(person_start, person_end, "PERSON")])

    resolved = _detect(text, _fresh_session(), model)

    entity_types = {r.span.entity_type for r in resolved}
    assert entity_types == {"PERSON", "PAN"}


def test_tier1_wins_over_an_overlapping_tier2_span_the_build_md_gate_scenario() -> None:
    """BUILD.md's Phase 4 gate: 'a PAN inside a span Tier 2 calls ORG
    resolves per the documented rule' — Tier 1 wins, deterministic
    evidence over probabilistic evidence, regardless of the Tier-2
    span's length or how much of the text it claims."""
    text = f"Please invoice {_VALID_PAN} Textiles Pvt Ltd"
    # The fake model claims the whole company name, including the PAN
    # embedded inside it, as one ORG span - exactly the scenario
    # ARCHITECTURE.md names ("A checksum-validated PAN inside a GLiNER
    # ORG span is a PAN").
    org_start = text.index(_VALID_PAN)
    org_end = len(text)
    model = _FakeTier2Model([_match(org_start, org_end, "ORG")])

    resolved = _detect(text, _fresh_session(), model)

    assert len(resolved) == 1
    assert resolved[0].span.entity_type == "PAN"
    assert resolved[0].span.tier == 1


def test_same_type_tier2_overlap_resolves_to_the_longest_span() -> None:
    """Closes the 'known open item' from Phase 4 Task 1
    (`Tier2Detector`'s own docstring): a model returning two overlapping
    matches of the *same* entity type is resolved correctly by
    `precedence.resolve()`'s existing, generic algorithm - no special
    case needed anywhere in the cascade."""
    text = "Ramesh Kumar Sharma phoned"
    shorter = _match(0, 12, "PERSON")  # "Ramesh Kumar"
    longer = _match(0, 19, "PERSON")  # "Ramesh Kumar Sharma"
    model = _FakeTier2Model([shorter, longer])

    resolved = _detect(text, _fresh_session(), model)

    assert len(resolved) == 1
    assert resolved[0].span.start == 0
    assert resolved[0].span.end == 19


def test_tier2_ingress_recognition_works_the_same_as_tier1() -> None:
    """Ingress recognition is generic over any resolved span's text,
    regardless of which tier produced it - a name surrogate replayed on
    a later turn must not be treated as a fresh detection either."""
    session = _fresh_session()
    session.record_surrogate("Arjun Reddy", "PERSON", _NOW)
    text = "Noted: Arjun Reddy will attend"
    name_start = text.index("Arjun Reddy")
    name_end = name_start + len("Arjun Reddy")
    model = _FakeTier2Model([_match(name_start, name_end, "PERSON")])

    resolved = _detect(text, session, model)

    assert len(resolved) == 1
    assert resolved[0].is_ingress_surrogate is True


# --- Phase 4 Task 4: Tier-2 failures are gated by FAIL_MODE -----------------


def test_tier2_model_failure_with_fail_mode_open_falls_back_to_tier1_only(
    captured_records: list[logging.LogRecord],
) -> None:
    """`Tier2Model.find_entities()` itself raising (e.g. the model
    process failing) is ARCHITECTURE.md's 'Model unavailable' case.
    Under `open`, this call must not raise - it proceeds with whatever
    Tier 1 already found, and logs a WARNING recording that Tier 2 was
    skipped."""
    text = f"Ramesh Kumar's PAN is {_VALID_PAN}"
    model = _RaisingTier2Model(RuntimeError("model process crashed"))

    resolved = detect(text, _fresh_session(), model, "open", correlation_id=_CORRELATION_ID)

    assert [r.span.entity_type for r in resolved] == ["PAN"]
    formatter = PiiSafeFormatter()
    events = [json.loads(formatter.format(r))["event"] for r in captured_records]
    assert "detection.tier2_failed" in events


def test_tier2_model_failure_with_fail_mode_closed_raises_fail_closed_error() -> None:
    text = "Ramesh Kumar called yesterday"
    model = _RaisingTier2Model(RuntimeError("model process crashed"))

    with pytest.raises(FailClosedError) as exc_info:
        detect(text, _fresh_session(), model, "closed", correlation_id=_CORRELATION_ID)

    assert isinstance(exc_info.value.__cause__, RuntimeError)


def test_tier2_offset_error_with_fail_mode_open_falls_back_to_tier1_only() -> None:
    """A bad model offset (`DetectionError`, raised inside
    `Tier2Detector.detect()`) is gated the same way a raw model failure
    is - both are "the Tier-2 stage failed" from the cascade's point of
    view."""
    text = f"Aadhaar {_VALID_AADHAAR}"
    out_of_bounds_model = _FakeTier2Model([_match(0, len(text) + 50, "PERSON")])

    resolved = detect(
        text, _fresh_session(), out_of_bounds_model, "open", correlation_id=_CORRELATION_ID
    )

    assert [r.span.entity_type for r in resolved] == ["AADHAAR"]


def test_tier2_offset_error_with_fail_mode_closed_raises_fail_closed_error() -> None:
    text = f"Aadhaar {_VALID_AADHAAR}"
    out_of_bounds_model = _FakeTier2Model([_match(0, len(text) + 50, "PERSON")])

    with pytest.raises(FailClosedError):
        detect(text, _fresh_session(), out_of_bounds_model, "closed", correlation_id=_CORRELATION_ID)


def test_a_tier2_failure_never_prevents_tier1_detection_from_running_first() -> None:
    """Tier 1 detection happens before Tier 2 is even attempted, so a
    Tier-2 failure - under either FAIL_MODE - can never suppress a Tier-1
    finding that was already computed."""
    text = f"PAN {_VALID_PAN}"
    model = _RaisingTier2Model(RuntimeError("model process crashed"))

    resolved = detect(text, _fresh_session(), model, "open", correlation_id=_CORRELATION_ID)

    assert len(resolved) == 1
    assert resolved[0].span.entity_type == "PAN"
