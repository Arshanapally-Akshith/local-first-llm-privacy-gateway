"""End-to-end proof, against the real running gateway (not
`cascade.detect()` in isolation — ARCHITECTURE.md's Adversarial
Evaluation section requires exactly this for the same reason
`tests/integration/test_sanitize_integration.py` proves the Phase 2
gate against the real app rather than the detectors alone), that
`adversarial.runner.run.run_case()` correctly distinguishes a caught
clean case from a leaked adversarial one.

Uses Tier-1-only bypass classes (`spaced_digits`, `split_across_turns`,
`pii_in_json_key`) so this module needs no real model and stays in the
default fast suite — `tests/conftest.py`'s autouse no-op Tier-2 stub
does not interfere here, since none of these three classes' mechanisms
depend on Tier-2 at all.
"""

from adversarial.cases.case_types import AdversarialCase
from adversarial.cases.pii_in_json_key import build_cases as build_pii_in_json_key_cases
from adversarial.cases.spaced_digits import build_cases as build_spaced_digits_cases
from adversarial.cases.split_across_turns import build_cases as build_split_across_turns_cases
from adversarial.runner.run import run_case


def _case_by_id(cases: list[AdversarialCase], case_id: str) -> AdversarialCase:
    matches = [case for case in cases if case.case_id == case_id]
    assert len(matches) == 1, f"expected exactly one case with id {case_id!r}, got {len(matches)}"
    return matches[0]


def test_clean_aadhaar_case_is_caught_by_the_real_gateway() -> None:
    case = _case_by_id(build_spaced_digits_cases(), "spaced_digits-AADHAAR-clean")
    result = run_case(case)
    assert result["caught"] is True
    assert result["structurally_valid_json"] is True
    assert result["original_absent"] is True
    assert result["replacement_present"] is True


def test_spaced_digits_adversarial_case_is_leaked_by_the_real_gateway() -> None:
    """The literal BUILD.md/ARCHITECTURE.md finding this suite exists to
    surface: a real bypass that still works, measured against the real
    gateway, not asserted from regex inspection alone."""
    case = _case_by_id(build_spaced_digits_cases(), "spaced_digits-AADHAAR-adversarial")
    result = run_case(case)
    assert result["caught"] is False
    assert result["structurally_valid_json"] is True


def test_split_across_turns_adversarial_case_is_leaked_by_the_real_gateway() -> None:
    """The system-level-only bypass ARCHITECTURE.md names explicitly —
    proven here against the real multi-message request, not a
    single-region detector call."""
    case = _case_by_id(
        build_split_across_turns_cases(), "split_across_turns-AADHAAR-adversarial"
    )
    result = run_case(case)
    assert result["caught"] is False


def test_pii_in_json_key_adversarial_case_is_leaked_by_the_real_gateway() -> None:
    case = _case_by_id(build_pii_in_json_key_cases(), "pii_in_json_key-AADHAAR-adversarial")
    result = run_case(case)
    assert result["caught"] is False


def test_prediction_matched_field_is_true_when_measured_outcome_matches_expectation() -> None:
    case = _case_by_id(build_spaced_digits_cases(), "spaced_digits-AADHAAR-clean")
    result = run_case(case)
    assert case.expected_outcome == "caught"
    assert result["prediction_matched"] is True
