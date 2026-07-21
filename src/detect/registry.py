"""The set of active Tier-1 and Tier-2 detectors.

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

from src.core.types import EntityType
from src.detect.detector import Detector
from src.detect.tier1.aadhaar import AadhaarDetector
from src.detect.tier1.card import CardDetector
from src.detect.tier1.email import EmailDetector
from src.detect.tier1.ifsc import IfscDetector
from src.detect.tier1.pan import PanDetector
from src.detect.tier1.phone import PhoneDetector
from src.detect.tier1.upi import UpiDetector
from src.detect.tier1.vehicle_registration import VehicleRegistrationDetector
from src.detect.tier2.detector import Tier2Detector
from src.detect.tier2.model import Tier2Model

_TIER1_DETECTORS: Final[tuple[Detector, ...]] = (
    AadhaarDetector(),
    CardDetector(),
    PanDetector(),
    IfscDetector(),
    UpiDetector(),
    VehicleRegistrationDetector(),
    EmailDetector(),
    PhoneDetector(),
)
"""Registration order matters beyond insertion convenience: it is the
tie-breaker ARCHITECTURE.md's Span Precedence rule uses between two
Tier-1 detectors that both claim an overlapping span ("longest match,
then registration order") — not consumed until Task 3, but the reason
this is a tuple (ordered, immutable) rather than a set.
"""

_TIER2_ENTITY_TYPES: Final[tuple[EntityType, ...]] = ("PERSON", "ORG", "ADDRESS")
"""BUILD.md's entire Phase 4 scope for Tier 2 — the fixed, closed set
`get_tier2_detectors()` always constructs, regardless of which model is
injected. Not `_TIER1_DETECTORS`'s shape (one constructed instance per
line): each entry here becomes one `Tier2Detector`, all three sharing
the *same* injected model reference — see `get_tier2_detectors()`.
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


def get_tier2_detectors(model: Tier2Model) -> Sequence[Detector]:
    """Return one `Tier2Detector` per Phase-4 entity type, all sharing
    `model`.

    Unlike `get_tier1_detectors()`, this is not a bare module-level
    constant: Tier-1 detectors are free to construct at import time
    because they have no external dependency at all, but a `Tier2Model`
    is expensive to build and must be injected (CLAUDE.md: "the NER
    model" is named explicitly among the things that must be
    dependency-injected, never reached for globally) — constructing it
    at import time would mean every test importing this module pays
    for a real model, or forces a fake one into a place tests never
    asked for it. Taking `model` as a parameter keeps this function
    itself cheap and pure; the model's own lifecycle (construct once,
    warm at startup) is Phase 4 Task 2's concern, not this registry's.

    Called fresh each time a caller needs the detectors, not cached
    here — the three returned objects are thin, stateless wrappers
    (see `Tier2Detector`), cheap enough that caching this function's
    own output would be an optimisation with nothing measured to
    justify it.
    """
    return tuple(
        Tier2Detector(entity_type=entity_type, model=model) for entity_type in _TIER2_ENTITY_TYPES
    )
