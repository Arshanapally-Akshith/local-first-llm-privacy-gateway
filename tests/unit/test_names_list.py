"""src.session.names: sanity checks on the production-sized `PERSON`
candidate list itself (Phase 4 Task 5) — not the allocator (see
test_session_names.py)."""

from src.session.names import DEFAULT_NAME_CANDIDATES


def test_candidates_are_non_empty() -> None:
    assert len(DEFAULT_NAME_CANDIDATES) > 0


def test_candidates_contain_no_duplicates() -> None:
    assert len(set(DEFAULT_NAME_CANDIDATES)) == len(DEFAULT_NAME_CANDIDATES)


def test_candidates_are_all_non_empty_strings() -> None:
    assert all(isinstance(name, str) and name.strip() for name in DEFAULT_NAME_CANDIDATES)


def test_candidates_are_production_sized() -> None:
    """ARCHITECTURE.md's own collision-math illustration targets
    "a ~5,000-name list" — Phase 3's placeholder (40 entries) is gone."""
    assert len(DEFAULT_NAME_CANDIDATES) >= 5000


def test_every_candidate_is_two_space_separated_tokens() -> None:
    """"First Last" shape, consistently — required for
    `test_sanitize.py`'s and `test_phase_3_gate.py`'s own
    `surrogate.split(" ")` assumptions to hold for *any* allocated
    candidate, not just the ones a given test happens to draw."""
    assert all(len(name.split(" ")) == 2 for name in DEFAULT_NAME_CANDIDATES)
