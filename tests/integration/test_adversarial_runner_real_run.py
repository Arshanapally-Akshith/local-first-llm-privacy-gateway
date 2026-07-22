"""`adversarial.runner.run.build_report()`: the real orchestration —
every discovered case (including `transliterated_names`, the one
Tier-2/GLiNER-dependent class) against the real, running gateway.
`real_model`-marked, mirroring
`tests/integration/test_runner_real_run.py`'s identical role for the
Phase 5 benchmark runner.

Also removes the default no-op Tier-2 override (`tests/conftest.py`'s
autouse fixture) for this module only, the same way
`test_phase_4_gate.py` does — every case in this suite runs against the
real, running gateway per ARCHITECTURE.md's Adversarial Evaluation
section, and a case whose bypass class depends on Tier-2
(`transliterated_names`) would otherwise silently measure a stub
instead of the real model.
"""

import pytest

from adversarial.runner.run import build_report, render_markdown
from app.main import app
from src.detect.tier2.gliner_model import get_tier2_model

pytestmark = pytest.mark.real_model


@pytest.fixture(autouse=True)
def _use_real_tier2_model() -> None:
    app.dependency_overrides.pop(get_tier2_model, None)


def test_build_report_runs_every_discovered_case_and_produces_a_valid_report() -> None:
    report = build_report()

    assert report["commit"]  # non-empty - either a real hash or "unknown"
    assert report["total_cases"] == len(report["cases"])
    assert report["total_cases"] > 0
    assert "transliterated_names" in report["classes"]

    for class_recall in report["classes"].values():
        for recall in (class_recall["clean_recall"], class_recall["adversarial_recall"]):
            assert recall is None or 0.0 <= recall <= 1.0


def test_render_markdown_reports_clean_and_adversarial_recall_separately_never_averaged() -> None:
    report = build_report()
    text = render_markdown(report)
    for bypass_class, class_recall in report["classes"].items():
        assert bypass_class in text
    # the two recall numbers must both appear as their own figures, not
    # a single combined/averaged one - spot-check one concrete class.
    spaced = report["classes"]["spaced_digits"]
    assert spaced["clean_recall"] is not None
    assert spaced["adversarial_recall"] is not None
    assert f"{spaced['clean_recall']:.2f}" in text
    assert f"{spaced['adversarial_recall']:.2f}" in text


def test_render_markdown_lists_every_bypass_that_still_works() -> None:
    """BUILD.md: "the bypasses that still work stay in the results
    file." Every adversarial case this run measured as not-caught must
    appear in the rendered "Bypasses that still work" section, by
    case_id — never hidden."""
    report = build_report()
    text = render_markdown(report)
    still_work = [c for c in report["cases"] if c["label"] == "adversarial" and not c["caught"]]
    assert len(still_work) > 0  # this suite's whole premise: some bypasses do work
    for case in still_work:
        assert case["case_id"] in text


def test_render_markdown_states_the_single_bypass_scope() -> None:
    report = build_report()
    text = render_markdown(report)
    assert "single-bypass" in text.lower()


def test_render_markdown_is_a_pure_function_of_the_report() -> None:
    report = build_report()
    text = render_markdown(report)
    assert render_markdown(report) == text
