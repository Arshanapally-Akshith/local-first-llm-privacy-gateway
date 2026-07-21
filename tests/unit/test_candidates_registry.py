"""src.session.candidates: the entity-type -> candidate-pool registry
(Phase 4 Task 5), mirroring src/surrogate/registry.py's own test shape
for the FF1 side."""

import pytest

from src.session.addresses import DEFAULT_ADDRESS_CANDIDATES
from src.session.candidates import NAME_MAP_ENTITY_TYPES, get_candidates, max_candidate_length
from src.session.names import DEFAULT_NAME_CANDIDATES
from src.session.org_names import DEFAULT_ORG_CANDIDATES


def test_name_map_entity_types_is_exactly_person_org_address() -> None:
    assert NAME_MAP_ENTITY_TYPES == {"PERSON", "ORG", "ADDRESS"}


def test_get_candidates_returns_the_right_pool_per_type() -> None:
    assert get_candidates("PERSON") == DEFAULT_NAME_CANDIDATES
    assert get_candidates("ORG") == DEFAULT_ORG_CANDIDATES
    assert get_candidates("ADDRESS") == DEFAULT_ADDRESS_CANDIDATES


def test_get_candidates_raises_key_error_for_a_non_name_map_type() -> None:
    with pytest.raises(KeyError):
        get_candidates("AADHAAR")


def test_max_candidate_length_is_the_true_maximum_across_all_pools() -> None:
    expected = max(
        max(len(c) for c in DEFAULT_NAME_CANDIDATES),
        max(len(c) for c in DEFAULT_ORG_CANDIDATES),
        max(len(c) for c in DEFAULT_ADDRESS_CANDIDATES),
    )
    assert max_candidate_length() == expected


def test_max_candidate_length_is_driven_by_address_not_person() -> None:
    """The reason `REQUIRED_WINDOW_LOOKAHEAD` had to widen beyond
    `PERSON`-only in Phase 4 Task 5: addresses are structurally longer
    than "First Last" names."""
    assert max(len(c) for c in DEFAULT_ADDRESS_CANDIDATES) > max(
        len(c) for c in DEFAULT_NAME_CANDIDATES
    )
