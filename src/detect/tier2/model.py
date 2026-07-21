"""The Tier-2 model seam (Phase 4 Task 1) — no real model yet.

`Tier2Model` is what `Tier2Detector` (`detector.py`) depends on, and
what a real GLiNER-class wrapper will implement once one is chosen
(Phase 4 Task 2, still an open architectural decision — see
`docs/DECISIONS.md`). Nothing in this module, or anywhere reachable
from it, names a specific library: that choice is deliberately deferred,
and this Protocol is exactly the seam that lets the rest of Tier 2
(the detector wrapper, the registry, the cascade wiring, FAIL_MODE,
session allocation) be built and fully tested against a fake
implementation before a real model exists.

One model, three detectors: `PersonDetector`/`OrgDetector`/
`AddressDetector` (in practice, three `Tier2Detector` instances, one
per entity type — see `detector.py`) all share a single injected
`Tier2Model` reference, so the model is loaded and warmed exactly once
per process regardless of how many entity types Tier 2 covers. This is
"share the model implementation internally" applied literally: the
model lives at this layer, below the `Detector` protocol, invisible to
`cascade.py` and `registry.py`, which see three ordinary detectors and
nothing about how they're related.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from src.core.types import EntityType, Offset


@dataclass(frozen=True, slots=True)
class ModelEntityMatch:
    """One raw entity match, as reported by a `Tier2Model` — not yet a
    `Span`. Deliberately offsets-and-type only, the same domain-types-
    over-primitives discipline `Span` itself follows: no matched
    substring is carried here, so a raw model result holds no more of
    the actual text than a resolved detector output would.

    `start`/`end` are **untrusted** at this point — they come from an
    external model, not from Python's own regex engine over the same
    string, and are not yet checked against any particular text's
    length. `Tier2Detector.detect()` is what validates them against
    the text they claim to describe, before they ever become a `Span`
    (see `DetectionError` in `src/core/exceptions.py`).
    """

    start: Offset
    end: Offset
    entity_type: EntityType
    """Expected to be one of `PERSON`, `ORG`, `ADDRESS` in practice —
    Tier 2's whole scope (BUILD.md, Phase 4) — but not narrowed to a
    smaller type here: `EntityType` is already the closed vocabulary
    every detector emits, and inventing a second, narrower type for
    "just the Tier-2 subset" would be exactly the kind of ceremony
    CLAUDE.md warns against for a three-member distinction the calling
    code (`Tier2Detector`) already enforces by construction (see
    `registry.get_tier2_detectors()`)."""


class Tier2Model(Protocol):
    """The seam a real GLiNER-class wrapper implements. Structural
    (`Protocol`, not an ABC — mirrors `Detector`'s own choice, for the
    same reason: a fake test double needs no shared base class, only
    the shape).

    **Must be request-stateless.** `find_entities(text)` must not
    retain `text`, any substring of it, or any value derived from it
    beyond the call's own execution — no instance attribute, no
    module-level cache, nothing that could let one request's text leak
    into how a later, unrelated call behaves or what it can observe.
    The model's own weights are not "request state" in this sense
    (they're fixed, loaded once, identical for every call); anything
    that varies per call, keyed on that call's own `text`, is.

    This is an explicit architectural constraint, not a style
    preference: a future optimisation that wants to memoise or batch
    across calls (e.g. because three `Tier2Detector` instances querying
    the same text independently proves, by measurement, to be a real
    cost) must either keep whatever it retains scoped to one request
    (never outliving the call that populated it) or be demonstrably
    thread-safe with a bounded, reviewed retention policy — and either
    way needs an explicit architectural review before it lands, not a
    silent addition. No such mechanism exists yet, and none should be
    added speculatively (CLAUDE.md: "no optimization without a
    before-number").

    Implementations are injected, never reached for globally
    (CLAUDE.md: "the NER model" is named explicitly among the things
    that must be dependency-injected) — constructed once per process,
    shared by every `Tier2Detector` instance that needs it.
    """

    def find_entities(self, text: str) -> Sequence[ModelEntityMatch]:
        """Return every entity match found in `text`, across whatever
        entity types this model detects — not filtered to any one
        type. `Tier2Detector` (one instance per entity type) is
        responsible for keeping only the matches its own `entity_type`
        cares about.

        One call per distinct `text`, always — never assume a caller
        has deduplicated repeated calls for the same string; per the
        class docstring, this method has nothing to remember between
        calls even if a caller does invoke it more than once for
        identical input.

        Precondition: none — must accept any `str`, including empty.
        Finding nothing is normal, not exceptional, and is represented
        by an empty sequence, matching `Detector.detect()`'s own
        contract (CLAUDE.md, Error Handling: "A detector finding
        nothing is normal").
        """
        ...
