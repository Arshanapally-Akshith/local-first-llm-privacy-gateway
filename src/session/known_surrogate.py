"""The known-surrogate registry entry — what a session remembers about
a value *it minted*, never about a real value.

This is new session state for structured (Tier-1) entities, which were
previously 100% stateless (FF1 needs no map to encrypt or decrypt).
Phase 3 needs *some* per-session record of "this exact string is a
surrogate we produced" so a later turn's request containing that same
string can be recognised and passed through instead of re-encrypted
(BUILD.md, Phase 3: "Ingress surrogate recognition... do not
re-encrypt"). See docs/DECISIONS.md for why this does not reintroduce
"a map for Tier 1" in the sense the frozen architecture table means:
the key here is always a surrogate (fake by construction, safe to hold
and log — ARCHITECTURE.md, Logging Architecture), never a real value,
and nothing here is invertible except by the same stateless FF1 key
every caller already has.
"""

from dataclasses import dataclass
from datetime import datetime

from src.core.types import EntityType


@dataclass(frozen=True, slots=True)
class KnownSurrogate:
    """Metadata about one surrogate value a session has minted.

    Deliberately a typed record, not a bare `entity_type` value keyed
    by the surrogate string alone: a future task is expected to need
    more than the type (e.g. which tier resolved it, for logging
    parity with `Span`; or a `used_at` timestamp, for the rehydration-
    fidelity harness). Adding a field here later is additive to this
    dataclass, not a signature change at every call site that already
    holds a `KnownSurrogate`.

    Frozen: a record of what was minted must not be mutated in place
    after the fact — the same discipline `Span` already applies to
    detected spans, for the same reason (CLAUDE.md: "Substitution
    happens at these exact offsets, so a span silently mutated... is
    exactly the kind of bug that corrupts a request body without
    raising anywhere near the corruption" — the analogous risk here is
    a registry entry silently drifting from what was actually minted).
    """

    entity_type: EntityType
    created_at: datetime
    """When this surrogate was minted, per the injected `Clock` — never
    `datetime.now()` read here directly. Not currently used for
    anything beyond being available (no eviction or reporting logic
    reads it yet); recorded now because retrofitting a timestamp onto
    every already-minted surrogate later is strictly harder than
    carrying one from the start."""
