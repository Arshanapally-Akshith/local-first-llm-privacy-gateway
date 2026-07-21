"""src.session.org_names: sanity checks on the `ORG` candidate list
itself (Phase 4 Task 5), mirroring test_names_list.py."""

from src.session.org_names import DEFAULT_ORG_CANDIDATES


def test_candidates_are_non_empty() -> None:
    assert len(DEFAULT_ORG_CANDIDATES) > 0


def test_candidates_contain_no_duplicates() -> None:
    assert len(set(DEFAULT_ORG_CANDIDATES)) == len(DEFAULT_ORG_CANDIDATES)


def test_candidates_are_all_non_empty_strings() -> None:
    assert all(isinstance(name, str) and name.strip() for name in DEFAULT_ORG_CANDIDATES)


def test_candidates_are_production_sized() -> None:
    assert len(DEFAULT_ORG_CANDIDATES) >= 4500


def test_no_candidate_is_a_real_well_known_company_name() -> None:
    """The reasoning this list's own module docstring gives for
    excluding real brands: a surrogate that happens to *be* a specific,
    identifiable real company is a materially worse residual than a
    low-probability shape coincidence."""
    real_companies = {"Tata", "Infosys", "Wipro", "Reliance", "Adani", "Birla", "Mahindra", "Godrej"}
    for candidate in DEFAULT_ORG_CANDIDATES:
        root = candidate.split(" ")[0]
        assert root not in real_companies
