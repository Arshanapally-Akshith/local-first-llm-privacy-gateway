"""The real Tier-2 model (Phase 4 Task 2): `gliner_multi_pii-v1`,
chosen after a measured evaluation against `gliner_small-v2.1` and
other GLiNER-class checkpoints — concentrated ADDRESS-recall and
false-positive-rate improvements on a synthetic corpus, weighed
against its larger RAM footprint (see `docs/DECISIONS.md`, Phase 4
Task 2, for the full comparison).

Implements `Tier2Model` (`src/detect/tier2/model.py`) — nothing above
this module (`Tier2Detector`, `registry.get_tier2_detectors()`,
`cascade.py`) needs to change now that a real model exists; this is
exactly the seam Phase 4 Task 1 built for.
"""

from collections.abc import Sequence
from functools import lru_cache
from typing import Final

from src.core.config import get_settings
from src.core.types import EntityType, Offset
from src.detect.tier2.model import ModelEntityMatch, Tier2Model

_GLINER_LABEL_TO_ENTITY_TYPE: Final[dict[str, EntityType]] = {
    "person": "PERSON",
    "organization": "ORG",
    "address": "ADDRESS",
}
_GLINER_LABELS: Final[tuple[str, ...]] = tuple(_GLINER_LABEL_TO_ENTITY_TYPE)
"""GLiNER's own label vocabulary (lowercase, library-specific) — never
leaked past this module. Everything above this class speaks only in
this project's own `EntityType` (`PERSON`/`ORG`/`ADDRESS`)."""


class GLiNERTier2Model:
    """`Tier2Model` backed by `gliner.GLiNER`.

    Request-stateless per that Protocol's own requirement:
    `find_entities()` calls straight through to the underlying model's
    `predict_entities()` on every call and retains nothing about `text`
    once the call returns. The loaded weights (`self._model`) are the
    only thing held across calls — identical for every request, never
    derived from any single request's own text. No cache of any kind
    exists here; see `Tier2Model`'s own docstring for why one is not
    added speculatively.
    """

    def __init__(self, model_id: str) -> None:
        from gliner import GLiNER

        self._model = GLiNER.from_pretrained(model_id)

    def find_entities(self, text: str) -> Sequence[ModelEntityMatch]:
        if not text:
            return ()
        raw_matches = self._model.predict_entities(text, list(_GLINER_LABELS))
        return tuple(
            ModelEntityMatch(
                start=Offset(match["start"]),
                end=Offset(match["end"]),
                entity_type=_GLINER_LABEL_TO_ENTITY_TYPE[match["label"]],
            )
            for match in raw_matches
        )


@lru_cache
def get_tier2_model() -> Tier2Model:
    """FastAPI dependency / startup-warmup entry point: **one**
    `GLiNERTier2Model` per process, mirroring `get_key_provider()`'s and
    `get_session_store()`'s exact shape.

    Loading the model (`GLiNER.from_pretrained`) is the expensive part
    this caching exists for — constructing it fresh per request would
    make every request pay a multi-second load, defeating the entire
    point of warming it at startup (BUILD.md, Phase 4: "warm at startup
    so cold start never hides inside p50").
    """
    settings = get_settings()
    return GLiNERTier2Model(settings.ner_model)
