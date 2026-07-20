"""Distinct identifier and domain types.

NewType wrappers so an opaque identifier of one kind cannot be passed
where a different kind is expected without mypy --strict catching it.
NewType adds no runtime validation — it is erased at runtime — so it is
the right tool for genuinely-arbitrary-string identifiers (any string
is a legitimate CorrelationId), and the wrong tool for closed
vocabularies. `EntityType` uses a runtime-checked Literal instead, for
exactly that reason: entity types are a small fixed set where a caller
passing an arbitrary string is a real bug this project must catch even
outside mypy; correlation ids have no such fixed set to check against.

`EntityType` and `Tier` live here, not in `src/core/logging.py` where
they originated (Phase 0/1): they are the closed vocabulary every
detector emits, not a logging-specific concept, and `detect/` must be
able to depend on them without depending on the logging module.
`logging.py` now imports them from here.
"""

from dataclasses import dataclass
from typing import Final, Literal, NewType, get_args

CorrelationId = NewType("CorrelationId", str)
"""Opaque per-request identifier, assigned once at ingress by the proxy
and threaded through every log line for that request (CLAUDE.md,
Structured logging: "Every request carries a correlation id from
ingress through rehydration"). Generation happens in the proxy route
handler (Phase 1, Task 4); this type exists now because
`fail_mode.resolve_failure()` already needs to accept one.
"""

Offset = NewType("Offset", int)
"""A character index into a text region — not a bare `int`. Substitution
happens at exact offsets (CLAUDE.md: "Offsets are a type, not an int");
an `Offset` passed where a length or an unrelated count is expected is
exactly the class of bug that corrupts a JSON body, and this type gives
mypy --strict a chance to catch a subset of those mix-ups at the call
site, even though it cannot catch an off-by-one in the value itself —
see `Span.__post_init__` for the runtime check that covers that case.
"""

EntityType = Literal[
    "AADHAAR",
    "PAN",
    "IFSC",
    "UPI",
    "VEHICLE_REG",
    "CARD",
    "EMAIL",
    "PHONE",
    "PERSON",
    "ORG",
    "ADDRESS",
]
"""Closed vocabulary of entity types this gateway ever detects. Fixed
here as a Literal (not a bare str) so an invalid value fails validation
at a runtime boundary (see `src/core/logging.py::redact_safe`) rather
than silently being accepted — a caller cannot smuggle an arbitrary
string, including a real detected value, through a field typed this
way."""

ENTITY_TYPES: Final[frozenset[str]] = frozenset(get_args(EntityType))

Tier = Literal[1, 2]
"""Which detection tier resolved a span. Tier 1 = checksum/regex,
deterministic. Tier 2 = GLiNER NER, best-effort."""

TIERS: Final[frozenset[int]] = frozenset(get_args(Tier))


@dataclass(frozen=True, slots=True)
class Span:
    """A detected entity's location and type within one text region.

    Immutable and offset-based, not a tuple: CLAUDE.md — "Spans are a
    type, not a tuple. Offsets are a type, not an int." Substitution
    happens at these exact offsets, so a span silently mutated after
    detection (e.g. by a later pipeline stage adjusting `start` in
    place) is exactly the kind of bug that corrupts a request body
    without raising anywhere near the corruption.

    This is the per-detector output type only — `(start, end,
    entity_type, tier)`. It is deliberately not `ResolvedSpan` (which
    ARCHITECTURE.md's Detection Pipeline describes as also carrying
    `is_ingress_surrogate`): recognising an ingress surrogate requires
    session state that a single Tier-1 detector never sees, so that
    field belongs to pipeline-level orchestration (Phase 3), not to
    this type.

    Invariant: `0 <= start < end`. Checked at construction because
    mypy --strict cannot verify an arithmetic relationship between two
    `Offset` values — the type system stops here, and this is where a
    caught off-by-one in an overlapping-span calculation must be
    caught instead (CLAUDE.md: "prevented by the type system or it is
    not prevented").
    """

    start: Offset
    end: Offset
    entity_type: EntityType
    tier: Tier

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValueError(
                f"invalid span (start={self.start}, end={self.end}) for "
                f"entity_type={self.entity_type}: start must be >= 0 and end must be > start"
            )
