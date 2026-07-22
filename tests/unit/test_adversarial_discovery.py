"""`adversarial.cases.discovery.discover_cases` — the Staff Engineer
review's required extensibility mechanism: adding a bypass class must
require only a new module, never an edit to this function or the
runner (`docs/DECISIONS.md`, Phase 6)."""

import pytest

from adversarial.cases.discovery import discover_cases

_EXPECTED_BYPASS_CLASSES = {
    "spaced_digits",
    "number_words",
    "transliterated_names",
    "split_across_turns",
    "base64_encoding",
    "pii_in_code",
    "pii_in_json_key",
    "homoglyphs",
    "zero_width",
}


def test_discover_cases_finds_every_registered_bypass_class() -> None:
    cases = discover_cases()
    found_classes = {case.bypass_class for case in cases}
    assert found_classes == _EXPECTED_BYPASS_CLASSES


def test_discover_cases_skips_infrastructure_modules() -> None:
    """`case_types`, `verify`, `carrier`, and `discovery` itself define
    no `build_cases()` and must never contribute a phantom "bypass
    class" of their own name."""
    cases = discover_cases()
    found_classes = {case.bypass_class for case in cases}
    assert "case_types" not in found_classes
    assert "verify" not in found_classes
    assert "carrier" not in found_classes
    assert "discovery" not in found_classes


def test_discover_cases_every_case_id_is_globally_unique() -> None:
    cases = discover_cases()
    case_ids = [case.case_id for case in cases]
    assert len(case_ids) == len(set(case_ids))


def test_discover_cases_every_class_has_at_least_one_clean_and_one_adversarial_case() -> None:
    """BUILD.md: "clean recall and adversarial recall reported
    separately" - a class missing either label would silently report
    an undefined recall for that half."""
    cases = discover_cases()
    by_class: dict[str, set[str]] = {}
    for case in cases:
        by_class.setdefault(case.bypass_class, set()).add(case.label)
    for bypass_class, labels in by_class.items():
        assert labels == {"clean", "adversarial"}, f"{bypass_class} missing a label: {labels}"


def test_assert_unique_case_ids_raises_on_a_duplicate() -> None:
    """`discover_cases()` itself always operates over real,
    already-unique-by-construction case modules, so its duplicate check
    is exercised here directly against a hand-built collision instead
    of mocking `pkgutil`/`importlib` to fabricate one at the module
    level."""
    from adversarial.cases.case_types import AdversarialCase, VerificationOutcome
    from adversarial.cases.discovery import _assert_unique_case_ids

    def _always_caught(_captured: bytes) -> VerificationOutcome:
        return VerificationOutcome(True, True, True, "")

    duplicate = AdversarialCase(
        case_id="duplicate-id",
        bypass_class="fake",
        entity_type="AADHAAR",
        label="clean",
        request_body={},
        expected_outcome="caught",
        verify=_always_caught,
    )
    with pytest.raises(ValueError, match="duplicate adversarial case_id"):
        _assert_unique_case_ids([duplicate, duplicate])


def test_assert_unique_case_ids_accepts_distinct_ids() -> None:
    from adversarial.cases.case_types import AdversarialCase, VerificationOutcome
    from adversarial.cases.discovery import _assert_unique_case_ids

    def _always_caught(_captured: bytes) -> VerificationOutcome:
        return VerificationOutcome(True, True, True, "")

    case_a = AdversarialCase(
        case_id="a",
        bypass_class="fake",
        entity_type="AADHAAR",
        label="clean",
        request_body={},
        expected_outcome="caught",
        verify=_always_caught,
    )
    case_b = AdversarialCase(
        case_id="b",
        bypass_class="fake",
        entity_type="AADHAAR",
        label="adversarial",
        request_body={},
        expected_outcome="leaked",
        verify=_always_caught,
    )
    _assert_unique_case_ids([case_a, case_b])  # must not raise
