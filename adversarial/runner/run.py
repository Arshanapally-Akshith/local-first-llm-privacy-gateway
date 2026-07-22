"""The Phase 6 adversarial suite runner entrypoint.

Run with:
    python -m adversarial.runner.run

Writes `adversarial/results/latest.json` (the authoritative,
commit-stamped artifact) and `adversarial/results/latest.md` (a pure
rendering of the same data — regenerable from the JSON alone, mirroring
`benchmarks/runner/run.py`'s identical split). Every case runs against
the real, running FastAPI app end to end (ARCHITECTURE.md's Adversarial
Evaluation section: "executed against the live gateway... because
bypasses like split-across-turns only exist at the system level"), not
against `cascade.detect()` in isolation — see `adversarial/__init__.py`.

Scope, stated once here and repeated in every rendered report so it is
never assumed away by a future reader: **this phase evaluates
single-bypass attacks only.** Combining two obfuscations in one case
(base64 plus zero-width, split-across-turns plus a homoglyph, ...) is
out of scope — nothing in this runner or its case modules has been
measured against combined obfuscation, and the results below must not
be read as though it had been.

Like `benchmarks/runner/run.py`, this module does not touch a top-level
`README.md` — Phase 8 owns assembling that; this phase's job is the
mechanism and the artifact Phase 8 will read from.
"""

import json
import logging
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Final, TypedDict

from fastapi.testclient import TestClient

from app.main import app
from src.core.types import ENTITY_TYPES
from src.mock_upstream.main import app as mock_app

from adversarial.cases.case_types import AdversarialCase
from adversarial.cases.discovery import discover_cases
from adversarial.runner.gateway_client import capturing_mock_upstream

_logger = logging.getLogger("adversarial.runner")
_logger.setLevel(logging.INFO)
_logger.addHandler(logging.StreamHandler())

_RESULTS_DIR: Final[Path] = Path(__file__).resolve().parent.parent / "results"
_JSON_PATH: Final[Path] = _RESULTS_DIR / "latest.json"
_MARKDOWN_PATH: Final[Path] = _RESULTS_DIR / "latest.md"

_SCOPE_NOTE: Final[str] = (
    "Scope: single-bypass attacks only. Every case below applies exactly one "
    "obfuscation technique. Combinations (e.g. base64 + zero-width, "
    "split-across-turns + homoglyph, or any other pairing of two classes in "
    "this suite) have not been measured and are out of scope for this phase — "
    "do not read a class's recall number as bounding performance against a "
    "combined attack."
)


class CaseResultSummary(TypedDict):
    case_id: str
    bypass_class: str
    entity_type: str
    label: str
    expected_outcome: str
    caught: bool
    structurally_valid_json: bool
    original_absent: bool
    replacement_present: bool
    prediction_matched: bool
    detail: str


class ClassCoverage(TypedDict):
    covered_entity_types: list[str]
    omitted_entity_types: list[str]


class ClassRecall(TypedDict):
    clean_recall: float | None
    clean_total: int
    clean_caught: int
    adversarial_recall: float | None
    adversarial_total: int
    adversarial_caught: int
    coverage: ClassCoverage


class AdversarialReport(TypedDict):
    """Deliberately carries no generation timestamp — mirroring
    `benchmarks/runner/run.py::BenchmarkReport`'s identical choice.
    `commit` is the only "when" this report needs: given the same
    commit's code, the same discovered cases, and the same live
    gateway behaviour, re-running this module must reproduce this
    report byte-for-byte (`discover_cases()`'s own sorted,
    OS-independent ordering is what makes that true of the `cases`
    list specifically — see that function's docstring). A wall-clock
    timestamp would make every regeneration differ trivially, for no
    informational gain a commit hash doesn't already provide, and
    would turn "rerun and diff" from a meaningful reproducibility check
    into one that always reports a false difference.
    """

    commit: str
    scope_note: str
    total_cases: int
    classes: dict[str, ClassRecall]
    cases: list[CaseResultSummary]


def _current_commit_hash() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).resolve().parent,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return completed.stdout.strip()


def run_case(case: AdversarialCase) -> CaseResultSummary:
    """Send `case.request_body` through the real, running gateway (via
    `TestClient`, a real ASGI call — not a mock of the route) with a
    capturing transport standing in for the mock upstream, then verify
    what was actually captured.

    Each case gets its own fresh session (`case.case_id` as the
    `X-Session-Id`) — cases must never share session state with each
    other; a name-map allocation or ingress-surrogate recognition
    leaking from one case into an unrelated one would silently
    contaminate that case's result.
    """
    with capturing_mock_upstream(app, mock_app) as capturing:
        client = TestClient(app, headers={"X-Session-Id": f"adversarial-{case.case_id}"})
        response = client.post("/v1/chat/completions", json=case.request_body)
        if response.status_code != 200:
            # A non-200 here is a real defect (a malformed case body, a
            # crashed detector, ...), not a scored miss - fail loud
            # rather than silently recording it as "leaked."
            raise RuntimeError(
                f"case {case.case_id!r} got HTTP {response.status_code} from the live "
                f"gateway, expected 200: {response.text[:500]}"
            )
        assert len(capturing.captured_bodies) == 1, (
            f"case {case.case_id!r}: expected exactly one upstream call, got "
            f"{len(capturing.captured_bodies)}"
        )
        outcome = case.verify(capturing.captured_bodies[0])

    expected_caught = case.expected_outcome == "caught"
    return CaseResultSummary(
        case_id=case.case_id,
        bypass_class=case.bypass_class,
        entity_type=case.entity_type,
        label=case.label,
        expected_outcome=case.expected_outcome,
        caught=outcome.caught,
        structurally_valid_json=outcome.structurally_valid_json,
        original_absent=outcome.original_absent,
        replacement_present=outcome.replacement_present,
        prediction_matched=outcome.caught == expected_caught,
        detail=outcome.detail,
    )


def _recall(caught: int, total: int) -> float | None:
    return None if total == 0 else caught / total


def _aggregate_classes(
    results: Sequence[CaseResultSummary],
) -> dict[str, ClassRecall]:
    by_class: dict[str, list[CaseResultSummary]] = {}
    for result in results:
        by_class.setdefault(result["bypass_class"], []).append(result)

    classes: dict[str, ClassRecall] = {}
    for bypass_class, class_results in sorted(by_class.items()):
        clean = [r for r in class_results if r["label"] == "clean"]
        adversarial = [r for r in class_results if r["label"] == "adversarial"]
        covered = sorted({r["entity_type"] for r in class_results})
        omitted = sorted(ENTITY_TYPES - set(covered))
        classes[bypass_class] = ClassRecall(
            clean_recall=_recall(sum(r["caught"] for r in clean), len(clean)),
            clean_total=len(clean),
            clean_caught=sum(r["caught"] for r in clean),
            adversarial_recall=_recall(sum(r["caught"] for r in adversarial), len(adversarial)),
            adversarial_total=len(adversarial),
            adversarial_caught=sum(r["caught"] for r in adversarial),
            coverage=ClassCoverage(covered_entity_types=covered, omitted_entity_types=omitted),
        )
    return classes


def build_report(cases: Sequence[AdversarialCase] | None = None) -> AdversarialReport:
    """Run every case (every discovered case, if `cases` is omitted)
    against the live gateway and return the full report.

    Kept separate from `main()` so tests can pass a small, fixed
    `cases` list without touching the filesystem or invoking git —
    mirroring `benchmarks/runner/run.py::build_report()`'s identical
    split.
    """
    if cases is None:
        cases = discover_cases()

    results = [run_case(case) for case in cases]
    for result in results:
        if not result["prediction_matched"]:
            _logger.info(
                "prediction mismatch: case=%s expected=%s actual_caught=%s",
                result["case_id"],
                result["expected_outcome"],
                result["caught"],
            )

    return AdversarialReport(
        commit=_current_commit_hash(),
        scope_note=_SCOPE_NOTE,
        total_cases=len(results),
        classes=_aggregate_classes(results),
        cases=results,
    )


def render_markdown(report: AdversarialReport) -> str:
    """Render `report` as markdown — a pure function of the report
    data, regenerable from a committed `latest.json` alone."""
    lines = [
        "# Phase 6 Adversarial Suite Results",
        "",
        f"Commit: `{report['commit']}`",
        f"Total cases: {report['total_cases']}",
        "",
        f"> {report['scope_note']}",
        "",
        "Clean and adversarial recall are reported separately per class and are "
        "never averaged — the gap between them is the finding.",
        "",
        "A case counts as *caught* only if all three hold: the captured upstream "
        "body is still valid JSON, the original sensitive value is absent from "
        "it, and something was actually substituted in its place (not merely "
        "deleted) — see `adversarial/cases/case_types.py::VerificationOutcome`.",
        "",
        "| Bypass class | Clean recall | Adversarial recall | Entity types covered | "
        "Entity types omitted |",
        "|---|---|---|---|---|",
    ]
    for bypass_class, class_recall in sorted(report["classes"].items()):
        clean_str = (
            "n/a"
            if class_recall["clean_recall"] is None
            else f"{class_recall['clean_recall']:.2f} "
            f"({class_recall['clean_caught']}/{class_recall['clean_total']})"
        )
        adversarial_str = (
            "n/a"
            if class_recall["adversarial_recall"] is None
            else f"{class_recall['adversarial_recall']:.2f} "
            f"({class_recall['adversarial_caught']}/{class_recall['adversarial_total']})"
        )
        covered = ", ".join(class_recall["coverage"]["covered_entity_types"])
        omitted = ", ".join(class_recall["coverage"]["omitted_entity_types"]) or "(none)"
        lines.append(
            f"| {bypass_class} | {clean_str} | {adversarial_str} | {covered} | {omitted} |"
        )
    lines.append("")
    lines.append(
        "Omission rationale for every class lives in that class's own module "
        "docstring (`adversarial/cases/<bypass_class>.py`), not only here."
    )
    lines.append("")

    still_work = [
        c for c in report["cases"] if c["label"] == "adversarial" and not c["caught"]
    ]
    lines.append(f"## Bypasses that still work ({len(still_work)})")
    lines.append("")
    if still_work:
        lines.append("| Case | Entity type | Detail |")
        lines.append("|---|---|---|")
        for case in still_work:
            lines.append(f"| {case['case_id']} | {case['entity_type']} | {case['detail']} |")
    else:
        lines.append("None — every adversarial case in this run was caught.")
    lines.append("")

    mismatches = [c for c in report["cases"] if not c["prediction_matched"]]
    lines.append(f"## Prediction mismatches ({len(mismatches)})")
    lines.append("")
    lines.append(
        "A mismatch means this suite's own predicted outcome "
        "(`AdversarialCase.expected_outcome`) did not match what was actually "
        "measured — reported here rather than silently corrected, per this "
        "project's own honesty standard."
    )
    lines.append("")
    if mismatches:
        lines.append("| Case | Predicted | Actual caught | Detail |")
        lines.append("|---|---|---|---|")
        for case in mismatches:
            lines.append(
                f"| {case['case_id']} | {case['expected_outcome']} | {case['caught']} | "
                f"{case['detail']} |"
            )
    else:
        lines.append("None — every case's predicted outcome matched what was measured.")
    lines.append("")

    lines.append("## Blind red-team")
    lines.append("")
    lines.append(
        "Not part of this automated report by design — see "
        "`adversarial/results/redteam.md` for the manual exercise's template "
        "and recording format, and its own contents once a session has been run."
    )
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    report = build_report()
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    _JSON_PATH.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    _MARKDOWN_PATH.write_text(render_markdown(report), encoding="utf-8")
    _logger.info("wrote %s and %s", _JSON_PATH, _MARKDOWN_PATH)


if __name__ == "__main__":
    main()
