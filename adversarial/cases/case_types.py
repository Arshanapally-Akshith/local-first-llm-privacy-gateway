"""The adversarial suite's own domain types — distinct from
`benchmarks/generate/dataset_types.py::BenchmarkExample` deliberately,
not an oversight: a `BenchmarkExample` is flat text plus gold spans,
built for in-process `cascade.detect()` scoring; a bypass case is a
full JSON request body plus a live-gateway verification procedure —
BUILD.md's own reason bypasses like split-across-turns "only exist at
the system level" is exactly why this shape cannot be `BenchmarkExample`
reused.

`VerificationOutcome` encodes the Staff Engineer review's required
success criterion: "needle disappeared" alone is not evidence of
sanitization. A case is only `caught` if *all three* hold — the
captured upstream body is still valid JSON, the original sensitive
value is absent from it, and something was actually put in its place
(not merely deleted, truncated, or the whole field blanked). See
`adversarial/cases/verify.py` for the three verifier builders that
produce this triple without ever hardcoding what a surrogate looks
like — CLAUDE.md: surrogate schemes are allowed to change; this
suite's success criterion must not depend on today's implementation.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from src.core.types import EntityType
from src.pipeline.field_walker import JSONValue

CaseLabel = Literal["clean", "adversarial"]
"""Which half of a paired case this is — BUILD.md: "clean recall and
adversarial recall reported separately, never averaged." Every bypass
class contributes at least one `"clean"` case (the entity in canonical
form — known, from Phases 2-5, to already be detectable) and at least
one `"adversarial"` case (the identical entity, obfuscated) so the
recall delta is attributable to the obfuscation alone, never to a
different carrier or a different entity value."""

ExpectedOutcome = Literal["caught", "leaked"]
"""The predicted result, recorded per BUILD.md's "each bypass class is
a runnable case with an expected-outcome record" — not the measured
result. The runner reports both the prediction and the actual measured
`VerificationOutcome.caught`, and flags any mismatch: a wrong
prediction is itself a disclosed, honest finding (e.g. a "predicted
leak" that GLiNER's multilingual training actually catches), never
something this suite hides by quietly changing the prediction after
the fact."""


@dataclass(frozen=True, slots=True)
class VerificationOutcome:
    """The result of checking one case's captured upstream bytes
    against the three-part success criterion. Every field is a fact
    about what was actually observed, never a value copied from what
    the case *expected* — `AdversarialCase.expected_outcome` is a
    separate, predicted field for exactly this reason.
    """

    structurally_valid_json: bool
    """The captured upstream body still parses as JSON. A `False` here
    is a hard failure of the gateway's own JSON-rebuild contract
    (`field_walker.rebuild()`'s stated invariant) — not a bypass
    finding — and should never happen; the runner treats it as
    fail-loud evidence of a real defect, not a scored miss."""

    original_absent: bool
    """The real, sensitive value (or, for the two structural-isolation
    classes, the reconstructable combination of its fragments/key) is
    not present anywhere in the captured upstream body."""

    replacement_present: bool
    """Proof that a *substitution* occurred, not merely a deletion:
    for slot-based cases, the text immediately surrounding the
    entity's known position is byte-identical to what was sent, and
    the text between those two anchors changed and is no longer equal
    to the original value. Never checks the replacement against a
    specific surrogate format or value — CLAUDE.md: "do not hardcode
    specific surrogate values, since the surrogate implementation may
    evolve." For the two structural-isolation classes (split-across-
    turns, PII-as-a-JSON-key), this field mirrors `original_absent`
    directly — see `adversarial/cases/verify.py`."""

    detail: str
    """Human-readable evidence for the results artifact — e.g. what
    the mismatched field actually contained. Never includes the real
    entity value itself (CLAUDE.md: no PII in logs or artifacts) —
    every case module is responsible for only ever putting *synthetic*
    values into `detail`, the same "synthetic data only" rule that
    governs the benchmark's own generated dataset."""

    @property
    def caught(self) -> bool:
        """`True` iff every element of the required three-part
        criterion held. A case that is not `caught` is a leak — either
        because the entity survived untouched (the common case) or,
        in principle, because the response was structurally broken
        (which the runner treats as a defect to investigate, not a
        silently-scored miss — see `structurally_valid_json`'s own
        docstring)."""
        return self.structurally_valid_json and self.original_absent and self.replacement_present


@dataclass(frozen=True, slots=True)
class AdversarialCase:
    """One runnable case: a full chat-completion request body, and the
    means to verify what the live gateway forwarded from it.

    `case_id` must be globally unique across every bypass-class module
    — `adversarial/cases/discovery.py` raises loudly on a collision
    rather than silently letting one case's result overwrite another's.
    """

    case_id: str
    bypass_class: str
    entity_type: EntityType
    label: CaseLabel
    request_body: JSONValue
    expected_outcome: ExpectedOutcome
    verify: Callable[[bytes], VerificationOutcome]
