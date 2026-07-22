"""`adversarial.cases.case_types.VerificationOutcome.caught` — the
three-part success criterion the Staff Engineer review required
(`docs/DECISIONS.md`, Phase 6): "needle disappeared" alone must never
be sufficient. Each test isolates exactly one of the three required
signals failing, proving `caught` genuinely requires all three, not a
majority or any single one."""

from adversarial.cases.case_types import VerificationOutcome


def test_caught_true_when_all_three_signals_hold() -> None:
    outcome = VerificationOutcome(
        structurally_valid_json=True,
        original_absent=True,
        replacement_present=True,
        detail="",
    )
    assert outcome.caught is True


def test_caught_false_when_json_invalid_even_if_other_two_hold() -> None:
    outcome = VerificationOutcome(
        structurally_valid_json=False,
        original_absent=True,
        replacement_present=True,
        detail="",
    )
    assert outcome.caught is False


def test_caught_false_when_original_present_even_if_other_two_hold() -> None:
    outcome = VerificationOutcome(
        structurally_valid_json=True,
        original_absent=False,
        replacement_present=True,
        detail="",
    )
    assert outcome.caught is False


def test_caught_false_when_no_replacement_present_even_if_other_two_hold() -> None:
    """The exact scenario the review's required change targets: the
    original value merely disappeared (e.g. truncated, or a field
    blanked) without anything having demonstrably replaced it."""
    outcome = VerificationOutcome(
        structurally_valid_json=True,
        original_absent=True,
        replacement_present=False,
        detail="",
    )
    assert outcome.caught is False


def test_caught_false_when_all_three_signals_fail() -> None:
    outcome = VerificationOutcome(
        structurally_valid_json=False,
        original_absent=False,
        replacement_present=False,
        detail="",
    )
    assert outcome.caught is False
