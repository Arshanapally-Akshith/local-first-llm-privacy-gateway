"""Registry mapping each name-map `EntityType` to its finite candidate
pool (Phase 4 Task 5).

Mirrors `src/surrogate/registry.py`'s shape on the *other* side of
ARCHITECTURE.md's Surrogate Architecture split: that registry looks up
a stateless FF1 domain by entity type; this one looks up the finite
candidate pool `Session.allocate_or_lookup_name()` needs for an
unbounded-domain entity type (name/org/address).

`NAME_MAP_ENTITY_TYPES` is the single source of truth for "which entity
types go through the session map, not FF1" — `src/pipeline/sanitize.py`
(allocate) and `src/pipeline/rehydrate.py` (look up) both import it from
here rather than each hardcoding their own copy of the same set
(CLAUDE.md: "no duplicated logic").
"""

from collections.abc import Sequence
from typing import Final

from src.core.types import EntityType
from src.session.addresses import DEFAULT_ADDRESS_CANDIDATES
from src.session.names import DEFAULT_NAME_CANDIDATES
from src.session.org_names import DEFAULT_ORG_CANDIDATES

_CANDIDATES_BY_TYPE: Final[dict[EntityType, tuple[str, ...]]] = {
    "PERSON": DEFAULT_NAME_CANDIDATES,
    "ORG": DEFAULT_ORG_CANDIDATES,
    "ADDRESS": DEFAULT_ADDRESS_CANDIDATES,
}

NAME_MAP_ENTITY_TYPES: Final[frozenset[EntityType]] = frozenset(_CANDIDATES_BY_TYPE)
"""The three Tier-2 entity types ARCHITECTURE.md's Surrogate
Architecture routes through the session name map rather than FF1 —
`PERSON`, `ORG`, `ADDRESS`. UPI and email are a separate, still-open
gap (`docs/DECISIONS.md`, 2026-07-20) — they are unbounded-domain too,
but have no candidate pool registered here; they continue to raise
`SurrogateDomainError` exactly as before this task."""


def get_candidates(entity_type: EntityType) -> Sequence[str]:
    """Return the finite candidate pool for a name-map entity type.

    Callers are expected to have already checked `entity_type in
    NAME_MAP_ENTITY_TYPES` — this is the same "detect() already decided
    the type" precondition `src/surrogate/registry.get_surrogate_domain()`
    relies on its own caller for. A plain `KeyError` (not a
    `GatewayError` subclass) on an unregistered type is an internal
    precondition violation, not a request-time failure mode a caller
    should ever observe.
    """
    return _CANDIDATES_BY_TYPE[entity_type]


def max_candidate_length() -> int:
    """The longest candidate string across every registered name-map
    type — used by `src/pipeline/rehydrate.py` to size the response-path
    sliding window's lookahead margin, mirroring
    `src/surrogate/registry.py::max_registered_surrogate_length()` for
    the FF1 side. `ADDRESS` candidates are materially longer than
    `PERSON`/`ORG` ones, which is exactly why this spans all three
    pools rather than assuming `PERSON`'s own length is the ceiling.
    """
    return max(
        len(candidate) for candidates in _CANDIDATES_BY_TYPE.values() for candidate in candidates
    )
