"""The detection cascade — Tier 1 today, Tier 2 in Phase 4.

Turns one text region into its final, non-overlapping, tier-attributed
span set: run every registered Tier-1 detector, then resolve overlaps
via the documented precedence rule (ARCHITECTURE.md, Component 4,
"Detection Pipeline"; the term "cascade" is ARCHITECTURE.md's own name
for this flow — see "The cascade").

Lives under `src/detect/`, not `src/pipeline/`: ARCHITECTURE.md's
layering diagram places `detect` as its own layer, a sibling of
`surrogate`/`session` beneath `pipeline` (orchestration). This module
is what makes `detect` a layer with an entry point of its own, rather
than a bag of registries `pipeline` would otherwise have to reach into
directly.

No session parameter yet. Ingress-surrogate recognition (Phase 3) will
extend `detect()`'s signature once session state exists to recognize a
prior surrogate and mark it pass-through — an addition when that phase
arrives, not a redesign of this one.
"""

from src.core.types import Span
from src.detect import precedence
from src.detect.registry import get_tier1_detectors


def detect(text: str) -> list[Span]:
    """Run the full Tier-1 cascade over `text` and resolve overlaps.

    Returns a non-overlapping, start-ascending span list — see
    `precedence.resolve()`'s postconditions, which this function
    inherits unchanged. An empty `text`, or one with no matches,
    returns `[]`: normal, not exceptional (CLAUDE.md, Error Handling).
    """
    spans_per_detector = [detector.detect(text) for detector in get_tier1_detectors()]
    return precedence.resolve(spans_per_detector)
