"""Dataset-level types — the benchmark's own domain types, distinct
from `src/core/types.py::Span`.

`GoldEntity` is deliberately not `Span` reused as-is: a gold label
carries the literal injected `value` (needed to audit the dataset and,
later, to drive per-entity-type diagnostics), and carries no `tier` —
tier is an attribute of a *detection*, not of a ground-truth label, and
giving gold entities a fake tier would invite a scorer to accidentally
compare "which tier resolved this" between gold and a prediction, which
is not a meaningful comparison. `start`/`end` reuse `Offset` and
`entity_type` reuses `EntityType` from `src/core/types.py` directly
(CLAUDE.md: "domain types over primitives" applies to this dataset the
same as it does to the gateway's own request path).
"""

from dataclasses import dataclass
from typing import Literal

from src.core.types import EntityType, Offset

Language = Literal["en", "hi_en"]
"""The two carrier-sentence varieties BUILD.md's Phase 5 names: plain
English, and Hindi/Telugu-English code-switched (romanized — see
`templates.py`'s module docstring for why no Devanagari/Telugu script
is used in this first dataset)."""


@dataclass(frozen=True, slots=True)
class GoldEntity:
    """One ground-truth entity span within one `BenchmarkExample`.

    Invariant: `0 <= start < end` (mirroring `Span.__post_init__`) and
    `end - start == len(value)` — the span's width must equal the
    injected value's own length, which is what "offsets exact by
    construction" actually means as a checkable property, not just a
    generation-time intention.
    """

    start: Offset
    end: Offset
    entity_type: EntityType
    value: str

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValueError(
                f"invalid gold entity span (start={self.start}, end={self.end}) for "
                f"entity_type={self.entity_type}: start must be >= 0 and end must be > start"
            )
        if self.end - self.start != len(self.value):
            raise ValueError(
                f"gold entity span width ({self.end - self.start}) does not match "
                f"len(value)={len(self.value)} for entity_type={self.entity_type}: "
                f"offsets were not computed from the injected value itself"
            )


@dataclass(frozen=True, slots=True)
class BenchmarkExample:
    """One generated benchmark example: a carrier sentence with every
    slot filled, plus the exact gold spans of what was injected.

    `template_id` is carried through for traceability — a scorer or a
    future diagnostic can group results by carrier template without
    needing to re-derive it from `text` — not because BUILD.md requires
    it, but because it is free at generation time and expensive to
    reconstruct later.
    """

    example_id: str
    template_id: str
    language: Language
    text: str
    entities: tuple[GoldEntity, ...]
