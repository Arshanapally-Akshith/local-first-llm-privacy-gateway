"""The detection cascade — Tier 1 and Tier 2 (Phase 4 Task 3).

Turns one text region into its final, non-overlapping, tier-attributed,
ingress-resolved span set: run every registered Tier-1 detector and
every registered Tier-2 detector, resolve overlaps via the documented
precedence rule, then check each surviving span against the session's
known-surrogate registry (ARCHITECTURE.md, Component 4, "Detection
Pipeline" — its own stated responsibilities are "run Tier 1, run Tier
2, resolve overlaps, recognise ingress surrogates and mark them
pass-through, emit tier-hit instrumentation"; the term "cascade" is
ARCHITECTURE.md's own name for this flow — see "The cascade").

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

`tier2_model` is a required parameter, not reached for globally
(CLAUDE.md: "the NER model" is named explicitly among the things that
must be dependency-injected) — its lifecycle (construct once, warm at
startup) belongs to `app/main.py`/`routes.py`, threaded down through
`sanitize()`, exactly like `key_provider` and `clock` already are.

Phase 4 Task 4 gates the Tier-2 detection step with `FAIL_MODE`: a
failure there (a bad model offset, or the model call itself failing)
is a real, named ARCHITECTURE.md failure mode ("Tier 2 timeout or
model failure → FAIL_MODE decides"), unlike Tier 1, whose regex-based
detectors have no failure mode to guard — `finditer` over a `str`
either returns matches or it doesn't; it does not raise. Only the
Tier-2 detection step is wrapped for this reason; Tier-1 detection,
`precedence.resolve()`, and ingress recognition are not.
"""

from dataclasses import dataclass

from src.core.fail_mode import FailMode, resolve_failure
from src.core.types import CorrelationId, Span
from src.detect import precedence
from src.detect.registry import get_tier1_detectors, get_tier2_detectors
from src.detect.tier2.model import Tier2Model
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


def detect(
    text: str,
    session: Session,
    tier2_model: Tier2Model,
    fail_mode: FailMode,
    *,
    correlation_id: CorrelationId,
) -> list[ResolvedSpan]:
    """Run the full Tier-1 + Tier-2 cascade over `text`, resolve
    overlaps, and mark any span that is already a known surrogate for
    `session`.

    Tier-1 detectors' output is built first, Tier-2's second — this
    ordering is what `precedence.resolve()`'s registration-order
    tie-break sees, but it only ever matters *within* a tier (Tier 1
    always outranks Tier 2 outright, per the tier field itself), so
    Tier-1-before-Tier-2 here changes nothing about which detector wins
    a cross-tier overlap. It does fix the tie-break order among Tier-2's
    own three detectors (PERSON, ORG, ADDRESS — `_TIER2_ENTITY_TYPES`'s
    order in `registry.py`) for the rare case two of them claim
    overlapping text.

    If the Tier-2 stage fails — a `DetectionError` from a bad model
    offset, or any other exception the model call itself raises —
    `fail_mode` decides what happens next (`src/core/fail_mode.py`):
    `open` logs a WARNING and this call proceeds with Tier-2
    contributing zero spans for `text` (Tier-1's own spans are
    unaffected — they were already computed before Tier-2 ran);
    `closed` raises `FailClosedError`, aborting this call entirely.
    Tier-1 detection itself is never gated this way — regex `finditer`
    over a `str` cannot fail — so this is the only stage wrapped.

    Ingress recognition is the last step, deliberately: precedence
    resolution operates on raw detector output and is unrelated to
    whether a span's text happens to already be a minted surrogate, so
    it runs first, unchanged, on the full candidate set; only the
    *final*, non-overlapping spans are checked against the session.

    Returns spans in the same non-overlapping, start-ascending order
    `precedence.resolve()` already guarantees. An empty `text`, or one
    with no matches, returns `[]`: normal, not exceptional (CLAUDE.md,
    Error Handling).

    Raises:
        FailClosedError: the Tier-2 stage failed and `fail_mode` is
            `"closed"` — chained from the original cause.
    """
    spans_per_detector = [detector.detect(text) for detector in get_tier1_detectors()]
    try:
        tier2_spans = [detector.detect(text) for detector in get_tier2_detectors(tier2_model)]
    except Exception as exc:  # noqa: BLE001 - see module docstring: the
        # Tier-2 model call is the one external, unenumerable-failure-mode
        # boundary in this function (ARCHITECTURE.md: "Tier 2 timeout or
        # model failure -> FAIL_MODE decides"). A third-party CPU NER
        # model's own failure modes (and `Tier2Detector`'s own
        # `DetectionError` for a bad offset) cannot be exhaustively named
        # the way httpx's client-boundary exceptions can
        # (`upstream_client.py`) - narrowing this catch to a specific type
        # would leave real, named failure modes unguarded. The catch is
        # scoped as tightly as possible in code, not in type: only this
        # one call is wrapped, nothing else in this function.
        resolve_failure(fail_mode, "detection.tier2_failed", correlation_id, exc)
        tier2_spans = []
    spans_per_detector += tier2_spans
    resolved_spans = precedence.resolve(spans_per_detector)
    return [
        ResolvedSpan(
            span=span,
            is_ingress_surrogate=session.lookup_surrogate(text[span.start : span.end]) is not None,
        )
        for span in resolved_spans
    ]
