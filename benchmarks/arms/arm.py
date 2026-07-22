"""The shared shape every ablation arm implements.

`Protocol`, not an ABC, mirroring `src/detect/detector.py::Detector`
exactly (CLAUDE.md: "Prefer Protocol over ABCs for seams" — an arm needs
no shared base-class behaviour, only a shared shape). `Prediction` itself
mirrors `src/core/types.py::Span`'s offset/type invariant, but is a
distinct type: an arm is not one of this gateway's own detectors, has no
`tier` (tier is this project's own cascade concept — Presidio and its
custom recognizers are not part of that taxonomy, even where a recognizer
happens to delegate to a Tier-1 `Detector` internally), and the entity
types an arm predicts are read against gold labels only by
`(start, end, entity_type)` — the exact criterion `docs/DECISIONS.md`
(2026-07-22) fixed before any arm existed.
"""

from dataclasses import dataclass
from typing import Protocol

from src.core.types import EntityType, Offset


@dataclass(frozen=True, slots=True)
class Prediction:
    """One entity an arm predicted, already translated into this
    project's own `EntityType` vocabulary — never a baseline's raw
    label (see `presidio_label_map.py`).

    Invariant: `0 <= start < end`, mirroring `Span.__post_init__` and
    `GoldEntity.__post_init__` — the same offset discipline applied a
    third time, to a third distinct type, because each type answers a
    different question (a detector's own output; a dataset's gold
    label; an arm's prediction) and conflating them was rejected in
    `benchmarks/generate/dataset_types.py`'s own design for the same
    reason it is rejected here.
    """

    start: Offset
    end: Offset
    entity_type: EntityType

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValueError(
                f"invalid prediction span (start={self.start}, end={self.end}) for "
                f"entity_type={self.entity_type}: start must be >= 0 and end must be > start"
            )


class Arm(Protocol):
    """Given raw text, return every predicted entity."""

    def predict(self, text: str) -> list[Prediction]:
        """Return every entity this arm detects in `text`, in this
        project's own `EntityType` vocabulary.

        Precondition: none — must accept any `str`, including an empty
        one. Postcondition: none of this arm's own implementation
        details (a baseline's raw label, its confidence score, which
        internal recognizer fired) survive into the returned
        `Prediction`s — only what a scorer needs to compare against
        gold.
        """
        ...
