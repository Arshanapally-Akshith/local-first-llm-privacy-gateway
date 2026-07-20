"""The seam every detector — Tier 1 today, Tier 2 in Phase 4 — implements.

`Protocol`, not an ABC (CLAUDE.md: "Prefer Protocol over ABCs for
seams"): a detector needs no shared base-class behaviour, only a shared
shape, and structural typing lets a test double satisfy this interface
without inheriting from anything defined here.
"""

from typing import Protocol

from src.core.types import EntityType, Span, Tier


class Detector(Protocol):
    """Detects every span of exactly one entity type in a text region.

    Single responsibility (CLAUDE.md SOLID: "a detector detects; it
    does not substitute, log, or decide precedence"): a `Detector` never
    produces a surrogate, never emits a log line, and never resolves an
    overlap against another detector's output. Those are the Surrogate
    Engine's, the PII-Safe Logger's, and Span Precedence's jobs,
    respectively.

    Every concrete detector is substitutable behind this one protocol,
    including whatever mock detectors later phases' tests need
    (CLAUDE.md SOLID: Liskov) — mypy --strict enforces the shape at
    every call site that annotates a value as `Detector`.
    """

    entity_type: EntityType
    tier: Tier

    def detect(self, text: str) -> list[Span]:
        """Return every span of `entity_type` found in `text`.

        Precondition: none — must accept any `str`, including an empty
        one. Finding nothing is the normal case, not an error, and is
        represented by an empty list, never `None` (CLAUDE.md, Error
        Handling: "A detector finding nothing is normal — return an
        empty result").

        Postcondition: every returned `Span` has `entity_type` and
        `tier` equal to this detector's own `entity_type`/`tier`.
        Spans returned by one call are not guaranteed non-overlapping
        with spans from a *different* detector — resolving cross-
        detector overlap is Span Precedence's job (Phase 2, Task 3),
        not this one's.
        """
        ...
