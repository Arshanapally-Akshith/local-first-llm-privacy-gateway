"""Exercises the real `gliner_multi_pii-v1` model chosen in Phase 4
Task 2 (see `docs/DECISIONS.md` for the measured evaluation that picked
it). Marked `real_model` and excluded from the default `pytest` run
(`pytest.ini`) - loads real weights (first run downloads them from
HuggingFace Hub), takes real wall-clock time, and needs real RAM.
Everything else in this test suite runs against a fake `Tier2Model`
(`tests/unit/test_tier2_detector.py`) and never needs this file at all.

Run explicitly:
    pytest -m real_model tests/integration/test_tier2_real_model.py
"""

import logging
from datetime import datetime, timezone

import pytest

import app.main as main_module
from src.core.types import CorrelationId, SessionId
from src.detect.cascade import detect
from src.detect.tier2.detector import Tier2Detector
from src.detect.tier2.gliner_model import GLiNERTier2Model, get_tier2_model
from src.session.session import Session

pytestmark = pytest.mark.real_model

_MODEL_ID = "urchade/gliner_multi_pii-v1"


def test_find_entities_detects_person_and_org_with_valid_offsets() -> None:
    model = GLiNERTier2Model(_MODEL_ID)
    text = "Ramesh Kumar works at Bharat Electronics Limited, 14 MG Road, Bengaluru."

    matches = model.find_entities(text)

    assert matches
    for match in matches:
        assert 0 <= match.start < match.end <= len(text)
    entity_types = {match.entity_type for match in matches}
    assert "PERSON" in entity_types
    assert "ORG" in entity_types


def test_find_entities_on_empty_string_returns_nothing() -> None:
    model = GLiNERTier2Model(_MODEL_ID)

    assert model.find_entities("") == ()


def test_get_tier2_model_is_a_cached_singleton() -> None:
    first = get_tier2_model()
    second = get_tier2_model()

    assert first is second


def test_tier2_detector_end_to_end_with_the_real_model() -> None:
    """Task 1's seam + Task 2's real model, together: a real
    `Tier2Detector`, backed by the real model, must still satisfy
    every invariant Task 1's fake-model tests already proved in
    isolation - valid offsets, correct type filtering."""
    model = get_tier2_model()
    detector = Tier2Detector(entity_type="PERSON", model=model)
    text = "Please contact Ramesh Kumar regarding the invoice."

    spans = detector.detect(text)

    assert len(spans) == 1
    assert spans[0].entity_type == "PERSON"
    assert spans[0].tier == 2
    assert text[spans[0].start : spans[0].end] == "Ramesh Kumar"


def test_startup_warmup_logs_a_structured_event_with_positive_latency(
    captured_records: list[logging.LogRecord],
) -> None:
    main_module._warm_tier2_model()

    events = [
        r for r in captured_records if getattr(r, "event", None) == "startup.tier2_model_warmed"
    ]
    assert len(events) == 1
    assert events[0].latency_ms > 0  # type: ignore[attr-defined]


def test_cascade_resolves_a_real_tier1_tier2_overlap_tier1_wins() -> None:
    """BUILD.md's Phase 4 gate scenario ('a PAN inside a span Tier 2
    calls ORG resolves per the documented rule'), proven against the
    *real* model - not the fake used throughout
    `tests/unit/test_cascade.py`. GLiNER's own labelling behaviour is
    outside this test's control (it may or may not actually fold the
    PAN into a proposed ORG span), so the assertion is written to hold
    either way: the PAN must always survive as a tier-1 span at its
    exact offsets, and nothing else in the resolved set may overlap
    those offsets - the only way that can be true is if Tier 1 already
    won every overlap Tier 2 proposed against it.
    """
    text = "Please share the PAN AAAPL1234C Textiles Pvt Ltd for verification."
    pan_start = text.index("AAAPL1234C")
    pan_end = pan_start + len("AAAPL1234C")
    session = Session(SessionId("real-model-cascade-test"), created_at=datetime.now(timezone.utc))

    resolved = detect(
        text, session, get_tier2_model(), "closed", correlation_id=CorrelationId("corr-real-model")
    )

    pan_spans = [r for r in resolved if r.span.entity_type == "PAN"]
    assert len(pan_spans) == 1
    pan_resolved = pan_spans[0]
    assert pan_resolved.span.tier == 1
    assert (pan_resolved.span.start, pan_resolved.span.end) == (pan_start, pan_end)
    for other in resolved:
        if other is pan_resolved:
            continue
        assert not (other.span.start < pan_end and pan_start < other.span.end)
