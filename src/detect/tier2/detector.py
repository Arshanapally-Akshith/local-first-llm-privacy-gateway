"""`Tier2Detector` — one `Detector`-conforming class, parameterized by
entity type, not three near-identical ones.

`PersonDetector`/`OrgDetector`/`AddressDetector` (BUILD.md's Phase 4
vocabulary) are three *instances* of this class, not three separate
class definitions: each instance's only difference from the others is
which `entity_type` it keeps, and CLAUDE.md's own threshold for when
repetition becomes a refactor ("twice is a coincidence, three times is
a refactor") applies directly to three class bodies whose only real
content would be a single constant. One parameterized class, three
registrations (`registry.get_tier2_detectors()`), keeps that shared
logic in one place while still presenting the registry and the cascade
with three ordinary, independent `Detector` objects — the "outward
architecture stays detector-oriented" requirement, met exactly.
"""

from src.core.exceptions import DetectionError
from src.core.types import EntityType, Span, Tier
from src.detect.tier2.model import Tier2Model


class Tier2Detector:
    """A `Detector` (see `src/detect/detector.py`) backed by a shared,
    injected `Tier2Model`.

    Holds a reference to the *same* model instance every other
    `Tier2Detector` in the process holds — the model is constructed
    and warmed exactly once (Phase 4 Task 2), never per detector, never
    per request. This class does no caching of its own and holds no
    per-call state: `detect()` calls straight through to
    `Tier2Model.find_entities()` every time, keeping the same
    request-stateless property `Tier2Model` itself requires (see that
    class's own docstring) — nothing here retains `text` either.
    """

    tier: Tier = 2

    def __init__(self, entity_type: EntityType, model: Tier2Model) -> None:
        self.entity_type = entity_type
        self._model = model

    def detect(self, text: str) -> list[Span]:
        """Return every span of `self.entity_type` found in `text`.

        `Tier2Model.find_entities()` returns matches across whatever
        types the model detects, undifferentiated — this method keeps
        only the ones matching `self.entity_type` and is what makes
        three separate `Tier2Detector` instances, each filtering the
        same shared call's-worth of model output to a different type,
        look like three ordinary, independent detectors to everything
        above this class.

        Raises:
            DetectionError: a kept match's offsets don't describe a
                valid position in `text` (negative, inverted, or past
                its end). The model's offsets are the first ones this
                codebase has ever had to trust from outside its own
                regex engine — Tier-1 detectors' offsets are always
                valid for the string being matched, by construction;
                a model's are not, and must be checked before becoming
                a `Span`, not after.

        If the model itself returns two *overlapping* matches of
        `self.entity_type` in one call, both are returned here
        unfiltered — this method does not deduplicate them. Resolved in
        Phase 4 Task 3: `precedence.resolve()`'s documented precondition
        ("no overlap within one detector's own output") turns out not to
        be load-bearing for correctness — its priority-and-eliminate
        algorithm operates on a flat `(span, detector_index)` list and
        eliminates *any* pairwise overlap regardless of whether both
        spans came from the same detector, so a same-detector overlap
        (longest wins, then original order) resolves exactly like a
        cross-detector one. See
        `tests/unit/test_cascade.py::test_same_type_tier2_overlap_resolves_to_the_longest_span`
        and `docs/DECISIONS.md`.
        """
        spans: list[Span] = []
        for match in self._model.find_entities(text):
            if match.entity_type != self.entity_type:
                continue
            if not (0 <= match.start < match.end <= len(text)):
                raise DetectionError(
                    f"Tier2Detector(entity_type={self.entity_type}) received an "
                    f"out-of-bounds match (start={match.start}, end={match.end}) "
                    f"for a text region of length {len(text)} - the model's "
                    "offsets do not describe a valid position in the text it "
                    "was given."
                )
            spans.append(
                Span(
                    start=match.start,
                    end=match.end,
                    entity_type=self.entity_type,
                    tier=self.tier,
                )
            )
        return spans
