"""src.session.names: sanity checks on the placeholder candidate list
itself — not the allocator (see test_session_names.py)."""

from src.session.names import DEFAULT_NAME_CANDIDATES


def test_candidates_are_non_empty() -> None:
    assert len(DEFAULT_NAME_CANDIDATES) > 0


def test_candidates_contain_no_duplicates() -> None:
    assert len(set(DEFAULT_NAME_CANDIDATES)) == len(DEFAULT_NAME_CANDIDATES)


def test_candidates_are_all_non_empty_strings() -> None:
    assert all(isinstance(name, str) and name.strip() for name in DEFAULT_NAME_CANDIDATES)
