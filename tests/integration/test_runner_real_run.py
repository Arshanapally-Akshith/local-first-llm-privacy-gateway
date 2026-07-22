"""benchmarks.runner.run.build_report(): the real orchestration — all
four real arms, real models, against a small real dataset sample.
`real_model`-marked, and the heaviest test module in this suite (loads
spaCy + GLiNER + constructs four arms).

Uses one instantiation per template (the same stride-sampling approach
as `tests/integration/test_scoring_real_arm.py`), not the full ~2,860
examples — a full run is what `python -m benchmarks.runner.run` itself
is for, not this test suite's job to repeat on every run.
"""

import pytest

from benchmarks.generate.build_dataset import build_dataset
from benchmarks.generate.templates import TEMPLATES
from benchmarks.runner.run import _ARM_FACTORIES, build_report, render_markdown

pytestmark = pytest.mark.real_model


def _one_example_per_template() -> tuple:
    examples = build_dataset()
    instantiations_per_template = len(examples) // len(TEMPLATES)
    return tuple(examples[i * instantiations_per_template] for i in range(len(TEMPLATES)))


def test_build_report_runs_all_four_arms_and_produces_a_valid_report() -> None:
    examples = _one_example_per_template()
    report = build_report(examples)

    assert report["dataset_size"] == len(examples)
    assert report["commit"]  # non-empty - either a real hash or "unknown"
    assert set(report["arms"]) == {key for key, _title, _factory in _ARM_FACTORIES}

    for arm_results in report["arms"].values():
        assert len(arm_results) > 0
        for summary in arm_results.values():
            assert 0.0 <= summary["precision"] <= 1.0
            assert 0.0 <= summary["recall"] <= 1.0
            assert 0.0 <= summary["f1"] <= 1.0
            assert summary["support"] == summary["true_positives"] + summary["false_negatives"]


def test_ours_arm_and_presidio_custom_arm_agree_on_tier1_types_in_the_real_report() -> None:
    # The same cross-arm property test_ours_arm.py already proved
    # directly - reconfirmed here at the report level, since this is
    # what a reader of the committed results artifact will actually see.
    examples = _one_example_per_template()
    report = build_report(examples)
    tier1_types = {"AADHAAR", "PAN", "IFSC", "UPI", "VEHICLE_REG"}
    for entity_type in tier1_types:
        if entity_type in report["arms"]["ours"] and entity_type in report["arms"]["presidio_custom"]:
            ours = report["arms"]["ours"][entity_type]
            custom = report["arms"]["presidio_custom"][entity_type]
            assert ours["true_positives"] == custom["true_positives"]
            assert ours["false_positives"] == custom["false_positives"]
            assert ours["false_negatives"] == custom["false_negatives"]


def test_render_markdown_on_a_real_report_produces_nonempty_well_formed_output() -> None:
    examples = _one_example_per_template()
    report = build_report(examples)
    text = render_markdown(report)
    assert "Arm 1" in text
    assert "Arm 4" in text
    assert str(report["dataset_size"]) in text
    assert render_markdown(report) == text  # regeneration from the same report is identical
