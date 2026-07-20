"""Span precedence — the documented overlap-resolution rule, once.

Resolves overlapping spans from any number of detectors into a single
non-overlapping set, per ARCHITECTURE.md's Span Precedence rule: Tier 1
always wins over Tier 2 on overlap ("deterministic evidence beats
probabilistic evidence, always"); among same-tier overlaps, the
longest match wins; ties are broken by detector registration order.

Registration order is threaded through `resolve()`'s argument shape,
not inferred from a flat list's incidental ordering: callers pass one
span sequence *per detector*, and that sequence's position in the
outer argument *is* the registration-order tie-breaker, folded
directly into the sort key. This makes determinism a property of the
algorithm's input shape rather than an unenforced calling convention a
caller could silently violate by, say, flattening two detectors'
output in the wrong order before calling in.
"""

from collections.abc import Sequence

from src.core.types import Span, Tier


def resolve(spans_per_detector: Sequence[Sequence[Span]]) -> list[Span]:
    """Resolve overlapping spans into a single non-overlapping set.

    `spans_per_detector[i]` is detector `i`'s own output, in whatever
    order that detector produced it; `i` itself is that detector's
    registration order, and is folded directly into the sort key
    below as the tie-breaker CLAUDE.md's precedence rule calls
    "registration order." Callers should build this argument the same
    way the registry itself is iterated, e.g.
    `[d.detect(text) for d in get_tier1_detectors()]`, so that `i`
    actually means what it claims to.

    Precondition: within any single `spans_per_detector[i]`, no two
    spans overlap each other. Every current detector satisfies this
    by construction (regex `finditer` never yields overlapping
    matches), so same-detector spans never compete against each other
    for this function's single flat priority tuple — only spans from
    *different* detectors do.

    Postconditions:
        - No two spans in the returned list overlap each other
          (`_spans_overlap` is false for every pair).
        - The returned list is sorted by `start`, ascending.
        - Deterministic: identical input (including which detector
          index each span sequence occupies) always produces an
          identical, identically-ordered output. Nothing in this
          function reads a clock, a source of randomness, or relies
          on `set`/`dict` iteration order.

    The winner of an overlap claims its *entire* conflict neighborhood,
    not just the specific span(s) it directly overlaps. If span B
    overlaps both A and C, but A and C do not overlap each other, and B
    outranks both, then accepting B eliminates A and C together — even
    though A and C could otherwise have coexisted. This is deliberate:
    "deterministic evidence beats probabilistic evidence, always" is an
    unconditional priority rule, not an optimisation for maximum
    surviving span count. A resolver that instead kept A and C because
    that covers more text would be making exactly the kind of judgment
    call precedence isn't supposed to make — see
    `test_chain_overlap_highest_priority_span_eliminates_both_neighbors`
    and its converse in the test suite.
    """
    indexed_spans: list[tuple[Span, int]] = [
        (span, detector_index)
        for detector_index, detector_spans in enumerate(spans_per_detector)
        for span in detector_spans
    ]

    def priority(item: tuple[Span, int]) -> tuple[Tier, int, int]:
        span, detector_index = item
        length = span.end - span.start
        return (span.tier, -length, detector_index)

    ranked = sorted(indexed_spans, key=priority)

    accepted: list[Span] = []
    for span, _detector_index in ranked:
        if not any(_spans_overlap(span, kept) for kept in accepted):
            accepted.append(span)

    return sorted(accepted, key=lambda span: span.start)


def _spans_overlap(a: Span, b: Span) -> bool:
    """True iff `a` and `b` share at least one character position.

    Half-open interval intersection (`a.start < b.end and b.start <
    a.end`): adjacent spans (`a.end == b.start`) are *not* overlapping
    under this definition. CLAUDE.md's off-by-one concern for span
    arithmetic lives entirely in this comparison, which is why it is
    a standalone, directly-tested function rather than inlined into
    `resolve()`.
    """
    return a.start < b.end and b.start < a.end
