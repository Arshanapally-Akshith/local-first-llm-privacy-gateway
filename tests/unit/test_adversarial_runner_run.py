"""`adversarial.runner.run`: `render_markdown()` — fast, pure-function
tests using a hand-built `AdversarialReport`, no live gateway or model
involved — and `discover_cases()`'s determinism guarantee, which is
what makes the real, live-gateway-produced report byte-reproducible
across machines and CI runs. `build_report()`'s own orchestration
(the real live-gateway run) is proved in
`tests/integration/test_adversarial_runner_real_run.py`.
"""

from adversarial.cases.discovery import discover_cases
from adversarial.runner.run import AdversarialReport, ClassCoverage, ClassRecall, render_markdown

_FAKE_REPORT: AdversarialReport = {
    "commit": "deadbeef",
    "scope_note": "Scope: single-bypass attacks only. Test note.",
    "total_cases": 4,
    "classes": {
        "spaced_digits": ClassRecall(
            clean_recall=1.0,
            clean_total=2,
            clean_caught=2,
            adversarial_recall=0.0,
            adversarial_total=2,
            adversarial_caught=0,
            coverage=ClassCoverage(
                covered_entity_types=["AADHAAR", "CARD"],
                omitted_entity_types=["PAN"],
            ),
        ),
    },
    "cases": [
        {
            "case_id": "spaced_digits-AADHAAR-clean",
            "bypass_class": "spaced_digits",
            "entity_type": "AADHAAR",
            "label": "clean",
            "expected_outcome": "caught",
            "caught": True,
            "structurally_valid_json": True,
            "original_absent": True,
            "replacement_present": True,
            "prediction_matched": True,
            "detail": "prefix/suffix invariant held; sent value replaced",
        },
        {
            "case_id": "spaced_digits-AADHAAR-adversarial",
            "bypass_class": "spaced_digits",
            "entity_type": "AADHAAR",
            "label": "adversarial",
            "expected_outcome": "leaked",
            "caught": False,
            "structurally_valid_json": True,
            "original_absent": True,
            "replacement_present": False,
            "prediction_matched": True,
            "detail": "prefix/suffix invariant held; sent value unchanged",
        },
    ],
}


def test_render_markdown_includes_the_commit_and_scope_note() -> None:
    text = render_markdown(_FAKE_REPORT)
    assert "deadbeef" in text
    assert "single-bypass" in text.lower()


def test_render_markdown_reports_clean_and_adversarial_recall_as_distinct_figures() -> None:
    text = render_markdown(_FAKE_REPORT)
    assert "1.00 (2/2)" in text
    assert "0.00 (0/2)" in text


def test_render_markdown_includes_coverage_and_omission() -> None:
    text = render_markdown(_FAKE_REPORT)
    assert "AADHAAR, CARD" in text
    assert "PAN" in text


def test_render_markdown_lists_the_leaked_adversarial_case() -> None:
    text = render_markdown(_FAKE_REPORT)
    assert "spaced_digits-AADHAAR-adversarial" in text
    assert "## Bypasses that still work (1)" in text


def test_render_markdown_reports_zero_mismatches_when_every_prediction_matched() -> None:
    text = render_markdown(_FAKE_REPORT)
    assert "## Prediction mismatches (0)" in text


def test_render_markdown_is_a_pure_function_of_the_report() -> None:
    assert render_markdown(_FAKE_REPORT) == render_markdown(_FAKE_REPORT)


def test_discover_cases_returns_cases_sorted_by_case_id() -> None:
    """The determinism guarantee `discover_cases()`'s own docstring
    describes: reproducible regardless of the filesystem's own
    directory-listing order, which is not guaranteed identical across
    operating systems."""
    case_ids = [case.case_id for case in discover_cases()]
    assert case_ids == sorted(case_ids)


def test_discover_cases_is_deterministic_across_repeated_calls() -> None:
    first_call_ids = [case.case_id for case in discover_cases()]
    second_call_ids = [case.case_id for case in discover_cases()]
    assert first_call_ids == second_call_ids
