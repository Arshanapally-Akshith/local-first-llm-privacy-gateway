"""benchmarks.generate.entity_values: every generator produces a value
that satisfies the *real* production constraint for its type — proved
by invoking the actual detector/checksum/candidate-pool code, never a
second implementation of the same rule (CLAUDE.md: "no duplicated
logic" — this is the test suite half of that requirement; the
generator module itself deliberately contains no self-validation, see
its own module docstring)."""

import random

from src.core.types import ENTITY_TYPES, Offset, Span
from src.detect import precedence
from src.detect.registry import get_tier1_detectors
from src.detect.tier1.checksum import luhn_is_valid, verhoeff_is_valid
from src.session.candidates import get_candidates

from benchmarks.generate import entity_values
from benchmarks.generate.entity_values import _phone_candidate_wins_precedence, generate_value

_TIER1_DETECTORS_BY_TYPE = {detector.entity_type: detector for detector in get_tier1_detectors()}
_STRUCTURED_TYPES = tuple(_TIER1_DETECTORS_BY_TYPE)
_NAME_MAP_TYPES = ("PERSON", "ORG", "ADDRESS")
_SEEDS = (0, 1, 2, 3, 42, 1000)


def test_every_entity_type_has_a_registered_generator() -> None:
    assert set(entity_values._GENERATORS) == set(ENTITY_TYPES)


def test_structured_values_round_trip_through_the_real_detector() -> None:
    """The strongest available proof of structural validity: the exact
    production `Detector` this value would face in the real pipeline
    detects it, at the exact offsets of the isolated string."""
    for entity_type in _STRUCTURED_TYPES:
        detector = _TIER1_DETECTORS_BY_TYPE[entity_type]
        for seed in _SEEDS:
            rng = random.Random(seed)
            value = generate_value(entity_type, rng)
            assert detector.detect(value) == [
                Span(start=Offset(0), end=Offset(len(value)), entity_type=entity_type, tier=1)
            ], f"{entity_type} value {value!r} (seed={seed}) was not detected as itself"


def test_aadhaar_is_verhoeff_valid_and_in_the_reserved_range() -> None:
    for seed in _SEEDS:
        value = generate_value("AADHAAR", random.Random(seed))
        assert len(value) == 12
        assert verhoeff_is_valid(value)
        assert value.startswith("9999"), (
            "gold Aadhaar values must be drawn from UIDAI's documented reserved "
            "9999-prefixed test-UID block (docs/DECISIONS.md, 2026-07-20), not the "
            "unrestricted issuable space"
        )


def test_card_is_luhn_valid() -> None:
    for seed in _SEEDS:
        value = generate_value("CARD", random.Random(seed))
        assert len(value) == 16
        assert luhn_is_valid(value)


def test_name_map_values_are_drawn_from_the_real_candidate_pools() -> None:
    for entity_type in _NAME_MAP_TYPES:
        pool = set(get_candidates(entity_type))
        for seed in _SEEDS:
            value = generate_value(entity_type, random.Random(seed))
            assert value in pool


def test_generation_is_deterministic_given_the_same_rng_state() -> None:
    for entity_type in ENTITY_TYPES:
        first = generate_value(entity_type, random.Random(7))
        second = generate_value(entity_type, random.Random(7))
        assert first == second


def test_generation_varies_across_rng_states_for_types_with_more_than_one_possible_value() -> None:
    # A sanity check that generators actually consume `rng` rather than
    # silently ignoring it and always returning one fixed value — every
    # type here has a large enough value space that two different seeds
    # producing the same value by chance is not something 6 seeds should
    # trigger.
    for entity_type in ENTITY_TYPES:
        values = {generate_value(entity_type, random.Random(seed)) for seed in _SEEDS}
        assert len(values) > 1, f"{entity_type} produced the same value across all seeds"


def test_phone_candidate_wins_precedence_rejects_known_colliding_values() -> None:
    # Two real values this generator itself produced before this fix,
    # confirmed to have actually been mis-attributed by the cascade
    # (docs/DECISIONS.md, 2026-07-22, "Phase 5 Task 7"): one
    # coincidentally Verhoeff-valid (collides with AADHAAR), one
    # coincidentally Luhn-valid (collides with CARD). Both must now be
    # rejected by the same check `_generate_phone()` retries against.
    assert _phone_candidate_wins_precedence("918298529155") is False  # Verhoeff-valid
    assert _phone_candidate_wins_precedence("917818830734") is False  # Luhn-valid


def test_phone_candidate_wins_precedence_accepts_an_ordinary_value() -> None:
    assert _phone_candidate_wins_precedence("09876543210") is True  # "0" prefix, 11 digits


def test_generated_phone_values_always_win_precedence_against_every_tier1_detector() -> None:
    """The end-to-end proof: run `generate_value("PHONE", ...)` across
    many seeds, then run the *actual cascade precedence step*
    (`get_tier1_detectors()` + `precedence.resolve()`, not just
    `PhoneDetector` in isolation — the isolated check is exactly what
    `test_structured_values_round_trip_through_the_real_detector` above
    already does, and exactly what *failed* to catch the original
    collision, since `PhoneDetector` alone always matches its own
    output regardless of what any other detector also claims) and
    confirm the resolved span is always `PHONE`, never re-attributed to
    another Tier-1 type.
    """
    for seed in range(200):
        value = generate_value("PHONE", random.Random(seed))
        spans_per_detector = [detector.detect(value) for detector in get_tier1_detectors()]
        resolved = precedence.resolve(spans_per_detector)
        assert resolved == [
            Span(start=Offset(0), end=Offset(len(value)), entity_type="PHONE", tier=1)
        ], f"seed={seed} produced {value!r}, resolved to {resolved}"
