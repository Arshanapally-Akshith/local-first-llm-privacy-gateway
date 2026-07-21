"""The rehydration-fidelity harness is code, and it gets tested too
(CLAUDE.md: "Benchmark and adversarial runners are code, and they get
tested too"). These tests check the taxonomy's transforms and the
runner's aggregation logic — not empirical hit-rate *values* beyond the
ones guaranteed by construction (exact/decorated always hit,
reasoned_about never can), since the whole point of the harness is to
measure the rest, not assert them.
"""

from rehydration_fidelity.runner.run import CategoryResult, build_report
from rehydration_fidelity.runner.taxonomy import SAMPLE_REAL_NAMES, TAXONOMY

_SURROGATE = "Arjun Reddy"


def _transform_for(category_name: str) -> object:
    for category in TAXONOMY:
        if category.name == category_name:
            return category.transform
    raise AssertionError(f"no taxonomy category named {category_name!r}")


def test_taxonomy_has_every_build_md_category_exactly_once() -> None:
    names = [category.name for category in TAXONOMY]

    assert names == [
        "exact",
        "decorated",
        "case_shifted",
        "partial",
        "abbreviated",
        "transliterated",
        "reasoned_about",
    ]


def test_exact_returns_the_surrogate_unchanged() -> None:
    assert _transform_for("exact")(_SURROGATE) == _SURROGATE  # type: ignore[operator]


def test_decorated_wraps_the_surrogate_in_markdown_emphasis() -> None:
    assert _transform_for("decorated")(_SURROGATE) == "**Arjun Reddy**"  # type: ignore[operator]


def test_case_shifted_changes_the_case() -> None:
    result = _transform_for("case_shifted")(_SURROGATE)  # type: ignore[operator]

    assert result != _SURROGATE
    assert result.upper() == result  # type: ignore[union-attr]


def test_partial_keeps_only_the_first_token() -> None:
    assert _transform_for("partial")(_SURROGATE) == "Arjun"  # type: ignore[operator]


def test_abbreviated_keeps_only_the_initial_and_last_name() -> None:
    assert _transform_for("abbreviated")(_SURROGATE) == "A. Reddy"  # type: ignore[operator]


def test_transliterated_shares_no_substring_with_the_original() -> None:
    result = _transform_for("transliterated")(_SURROGATE)  # type: ignore[operator]

    assert result != _SURROGATE
    assert "Arjun" not in result
    assert "Reddy" not in result


def test_transliterated_is_deterministic() -> None:
    transform = _transform_for("transliterated")

    assert transform(_SURROGATE) == transform(_SURROGATE)  # type: ignore[operator]


def test_reasoned_about_never_repeats_the_surrogate_verbatim() -> None:
    result = _transform_for("reasoned_about")(_SURROGATE)  # type: ignore[operator]

    assert _SURROGATE not in result
    assert "A" in result  # the surrogate's own first letter, per the transform's own logic


def test_category_result_hit_rate() -> None:
    assert CategoryResult(hits=3, total=4).hit_rate == 0.75


def test_category_result_hit_rate_on_zero_total_is_zero_not_a_division_error() -> None:
    assert CategoryResult(hits=0, total=0).hit_rate == 0.0


def test_build_report_has_every_category_with_the_full_sample_size() -> None:
    report = build_report()

    assert report["sample_size"] == len(SAMPLE_REAL_NAMES)
    categories = report["categories"]
    assert set(categories) == {category.name for category in TAXONOMY}  # type: ignore[arg-type]
    for result in categories.values():  # type: ignore[union-attr]
        assert result["total"] == len(SAMPLE_REAL_NAMES)


def test_build_report_exact_and_decorated_categories_always_fully_round_trip() -> None:
    """Guaranteed by the rehydration engine's own design (exact
    substring matching catches decoration for free — see
    tests/unit/test_rehydrate.py) — a regression here means the
    rehydration engine itself broke, not a finding to report."""
    report = build_report()

    assert report["categories"]["exact"]["hit_rate"] == 1.0  # type: ignore[index]
    assert report["categories"]["decorated"]["hit_rate"] == 1.0  # type: ignore[index]


def test_build_report_reasoned_about_never_round_trips() -> None:
    """Guaranteed by construction: the transform never repeats the
    surrogate verbatim, so exact-match rehydration cannot find it."""
    report = build_report()

    assert report["categories"]["reasoned_about"]["hit_rate"] == 0.0  # type: ignore[index]


def test_build_report_commit_field_is_a_non_empty_string() -> None:
    report = build_report()

    assert isinstance(report["commit"], str)
    assert report["commit"] != ""
