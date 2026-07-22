"""benchmarks.scoring against a real dataset slice and a real arm —
proves the scorer works end to end against real predictions and real
gold labels, not just the synthetic fixtures in
`tests/unit/test_scoring_score.py`. `real_model`-marked: constructs a
real `OurCascadeArm` (loads the real GLiNER model).

Uses a *sample* of the committed dataset (one instantiation per
template, via a stride slice — `build_dataset()` groups all 55
instantiations of one template consecutively, so `[::55]` is what
actually gives entity-type diversity; the first 20 *consecutive*
examples would all be the same single-entity-type template repeated),
not the full ~2,860 examples — running every example through a real
model is the Phase 5 runner's job (a later task), not this scorer
task's test suite.
"""

from datetime import datetime, timezone

import pytest

from src.core.fail_mode import FailMode
from src.core.types import CorrelationId, EntityType, SessionId
from src.detect.cascade import detect
from src.detect.tier1.checksum import verhoeff_is_valid
from src.detect.tier2.gliner_model import get_tier2_model
from src.session.session import Session

from benchmarks.arms.ours import OurCascadeArm
from benchmarks.generate.build_dataset import build_dataset
from benchmarks.generate.templates import TEMPLATES
from benchmarks.scoring.score import score_arm

pytestmark = pytest.mark.real_model

_TIER1_TYPES: tuple[EntityType, ...] = (
    "AADHAAR",
    "PAN",
    "IFSC",
    "UPI",
    "VEHICLE_REG",
    "CARD",
    "EMAIL",
    "PHONE",
)


def _one_example_per_template() -> tuple:
    examples = build_dataset()
    instantiations_per_template = len(examples) // len(TEMPLATES)
    return tuple(examples[i * instantiations_per_template] for i in range(len(TEMPLATES)))


def test_score_arm_against_a_real_dataset_sample_and_a_real_arm() -> None:
    examples = _one_example_per_template()
    arm = OurCascadeArm()
    report = score_arm(examples, arm)

    assert len(report) > 0
    for entity_type, entity_report in report.items():
        assert 0.0 <= entity_report.precision <= 1.0
        assert 0.0 <= entity_report.recall <= 1.0
        assert 0.0 <= entity_report.f1 <= 1.0
        assert entity_report.support >= 0


def test_our_cascade_recovers_every_tier1_type_with_perfect_recall_on_canonical_form() -> None:
    # ARCHITECTURE.md: "Tier 1 outputs are the only ones this system
    # calls guaranteed... if the entity is present in a canonical,
    # unobfuscated form, it is detected with certainty." This held for
    # seven of the eight Tier-1 types from the start; PHONE was the
    # exception until `benchmarks/generate/entity_values.py::_generate_phone()`
    # was fixed to reject any candidate a coincidental cross-type Tier-1
    # checksum collision would cause the cascade to re-attribute
    # (docs/DECISIONS.md, 2026-07-22, "Phase 5 Task 7" and its
    # follow-up entry) — every gold PHONE value in the committed dataset
    # is now guaranteed, by construction, to resolve as PHONE. All eight
    # types are asserted here together, not seven-plus-a-caveat.
    examples = _one_example_per_template()
    arm = OurCascadeArm()
    report = score_arm(examples, arm)
    for entity_type in _TIER1_TYPES:
        if entity_type in report and report[entity_type].support > 0:
            assert report[entity_type].recall == 1.0, f"{entity_type}: {report[entity_type]}"


def test_cascade_precedence_still_resolves_a_deliberately_colliding_value_correctly() -> None:
    # The dataset itself can no longer contain this case (the generator
    # rejects it), but the underlying cascade mechanism this project's
    # own fix relies on — "if two Tier-1 detectors validate the exact
    # same span, the earlier-registered one wins" — is still real
    # production behaviour and deserves its own direct regression proof,
    # independent of what the dataset happens to contain. A
    # deliberately-constructed adversarial value (not a random draw)
    # keeps this test meaningful regardless of what the generator does.
    # A "91"-prefixed phone number known to also be Verhoeff-valid
    # (found via the real generator during Task 7's investigation).
    colliding_value = "918298529155"
    assert verhoeff_is_valid(colliding_value), "fixture must actually collide, or this test proves nothing"

    prefix = "Please call "
    text = f"{prefix}{colliding_value} for confirmation."
    session = Session(SessionId("collision-probe"), created_at=datetime.now(timezone.utc))
    fail_mode: FailMode = "closed"
    resolved = detect(
        text, session, get_tier2_model(), fail_mode, correlation_id=CorrelationId("collision-probe")
    )
    matching_span_types = {r.span.entity_type for r in resolved if r.span.start == len(prefix)}
    # AADHAAR wins (registered before PhoneDetector in
    # src/detect/registry.py) - PHONE does not appear for this span.
    assert matching_span_types == {"AADHAAR"}
