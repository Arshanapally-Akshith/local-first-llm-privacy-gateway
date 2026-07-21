"""The detection cascade — Tier 1 today, Tier 2 in Phase 4.

Turns one text region into its final, non-overlapping, tier-attributed,
ingress-resolved span set: run every registered Tier-1 detector,
resolve overlaps via the documented precedence rule, then check each
surviving span against the session's known-surrogate registry
(ARCHITECTURE.md, Component 4, "Detection Pipeline" — its own stated
responsibilities are "run Tier 1, run Tier 2, resolve overlaps,
recognise ingress surrogates and mark them pass-through, emit tier-hit
instrumentation"; the term "cascade" is ARCHITECTURE.md's own name for
this flow — see "The cascade").

Lives under `src/detect/`, not `src/pipeline/`: ARCHITECTURE.md's
layering diagram places `detect` as its own layer, a sibling of
`surrogate`/`session` beneath `pipeline` (orchestration). This module
is what makes `detect` a layer with an entry point of its own, rather
than a bag of registries `pipeline` would otherwise have to reach into
directly. Depending on `session` here (for ingress recognition) is a
sibling-to-sibling dependency the layering diagram's arrows leave
unconstrained — it draws `pipeline -> detect/surrogate/session ->
core`, not a rule between the three siblings — and is where
ARCHITECTURE.md itself places this responsibility, not a layer above.

Individual `Detector` implementations remain entirely session-unaware
(Phase 3 architectural decision) — only this orchestration function
gains session context. A detector still only ever sees `text: str` and
returns spans; it has no way to know, and does not need to know,
whether a match is a real value or a surrogate this session already
minted.
"""

from dataclasses import dataclass

from src.core.types import Span
from src.detect import precedence
from src.detect.registry import get_tier1_detectors
from src.session.session import Session


@dataclass(frozen=True, slots=True)
class ResolvedSpan:
    """A detected `Span`, plus whether it is already a surrogate this
    session minted rather than a real value needing one.

    Wraps `Span` rather than extending or duplicating its fields
    (Phase 3 architectural decision): `Span` is a Phase 2 type several
    modules already depend on unchanged, and recognising an ingress
    surrogate needs session state a bare `Span` was deliberately never
    given access to (see `Span`'s own docstring in `src/core/types.py`).
    """

    span: Span
    is_ingress_surrogate: bool
    """`True` iff `session.lookup_surrogate()` already has an entry for
    this exact span's text — meaning some earlier turn in this same
    session minted it, and it must be passed through unchanged rather
    than re-encrypted (BUILD.md, Phase 3: "do not re-encrypt... a
    surrogate-of-a-surrogate unwinds one layer and corrupts silently").
    Exact string match only, via the same registry Task 1 built and
    Task 2 already writes name allocations into — conservative
    matching, not fuzzy, for the same rehydration-oracle reasoning that
    governs response-path matching (ARCHITECTURE.md, Response
    Lifecycle)."""


def detect(text: str, session: Session) -> list[ResolvedSpan]:
    """Run the full Tier-1 cascade over `text`, resolve overlaps, and
    mark any span that is already a known surrogate for `session`.

    Ingress recognition is the last step, deliberately: precedence
    resolution operates on raw detector output and is unrelated to
    whether a span's text happens to already be a minted surrogate, so
    it runs first, unchanged, on the full candidate set; only the
    *final*, non-overlapping spans are checked against the session.

    Returns spans in the same non-overlapping, start-ascending order
    `precedence.resolve()` already guarantees. An empty `text`, or one
    with no matches, returns `[]`: normal, not exceptional (CLAUDE.md,
    Error Handling).
    """
    spans_per_detector = [detector.detect(text) for detector in get_tier1_detectors()]
    resolved_spans = precedence.resolve(spans_per_detector)
    return [
        ResolvedSpan(
            span=span,
            is_ingress_surrogate=session.lookup_surrogate(text[span.start : span.end]) is not None,
        )
        for span in resolved_spans
    ]
