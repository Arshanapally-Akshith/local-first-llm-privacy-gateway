"""The set of active Tier-1 detectors.

Explicit, not import-time self-registration: a detector module that
registered itself as a side effect of being imported would make "which
detectors are active" depend on import order, which is untestable in
isolation and invisible at a glance. Adding a new Tier-1 type (Task 2)
is a one-line addition to `_TIER1_DETECTORS` below — this is what
CLAUDE.md's open/closed principle means for this registry: extension
without modifying any caller of `get_tier1_detectors()`.
"""

from collections.abc import Sequence
from typing import Final

from src.detect.detector import Detector
from src.detect.tier1.aadhaar import AadhaarDetector
from src.detect.tier1.card import CardDetector

_TIER1_DETECTORS: Final[tuple[Detector, ...]] = (
    AadhaarDetector(),
    CardDetector(),
)
"""Registration order matters beyond insertion convenience: it is the
tie-breaker ARCHITECTURE.md's Span Precedence rule uses between two
Tier-1 detectors that both claim an overlapping span ("longest match,
then registration order") — not consumed until Task 3, but the reason
this is a tuple (ordered, immutable) rather than a set.
"""


def get_tier1_detectors() -> Sequence[Detector]:
    """Return every registered Tier-1 detector, in registration order.

    Returns a `Sequence`, not a `list`: callers can iterate and index
    but not mutate the registry through the returned value, and the
    signature leaves room for a future `get_tier2_detectors()` /
    combined accessor without implying either returns something
    callers may append to.
    """
    return _TIER1_DETECTORS
