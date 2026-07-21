"""src.session.addresses: sanity checks on the `ADDRESS` candidate list
itself (Phase 4 Task 5), mirroring test_names_list.py."""

from src.session.addresses import DEFAULT_ADDRESS_CANDIDATES


def test_candidates_are_non_empty() -> None:
    assert len(DEFAULT_ADDRESS_CANDIDATES) > 0


def test_candidates_contain_no_duplicates() -> None:
    assert len(set(DEFAULT_ADDRESS_CANDIDATES)) == len(DEFAULT_ADDRESS_CANDIDATES)


def test_candidates_are_all_non_empty_strings() -> None:
    assert all(isinstance(name, str) and name.strip() for name in DEFAULT_ADDRESS_CANDIDATES)


def test_candidates_are_production_sized() -> None:
    assert len(DEFAULT_ADDRESS_CANDIDATES) >= 4500


def test_every_candidate_looks_like_a_house_number_street_city_address() -> None:
    for candidate in DEFAULT_ADDRESS_CANDIDATES:
        house_number, _, rest = candidate.partition(" ")
        assert house_number.isdigit()
        assert "," in rest  # street, city separator
