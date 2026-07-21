"""Rehydrate — the response-path counterpart to sanitize: surrogate ->
real value (CLAUDE.md vocabulary: "rehydrate — response path, surrogate
-> real").

Composes pieces earlier tasks built, the same way `sanitize.py` does for
the request path (CLAUDE.md: "no duplicated logic"): `Session`'s
known-surrogate registry (Phase 3 Task 1) says which strings this
session has minted and what type each is; `engine.decrypt()` (Phase 2)
inverts a Tier-1 (structured) surrogate statelessly; `Session.lookup_real_name()`
(Phase 3 Task 2) inverts a Tier-2 (name) surrogate via the session's own
map, since names have no stateless inverse.

Matching is exact-substring only, never fuzzy — the same
rehydration-oracle reasoning `Session.lookup_surrogate()` already
documents applies here with equal force (ARCHITECTURE.md, Response
Lifecycle: "Aggressive fuzzy matching means an attacker who learns the
surrogate distribution... induces the gateway to reinsert real PII into
attacker-readable output"). A surrogate the model returns decorated
(`**ABCDE1234F**`), embedded in a larger sentence, or repeated is still
an *exact* substring match — decoration wraps around a surrogate's own
contiguous characters, it never interleaves inside them, so exact
substring search catches every decorated/embedded form for free without
needing decoration-specific handling. Forms that break the surrogate's
own character sequence — `Arjun` alone (partial), `A. Reddy`
(abbreviated), a transliteration — do not match, and are not fixed here:
BUILD.md's rehydration-fidelity harness (a later task) is where the
per-category miss rate gets measured, not this module's job to close.

Where two known surrogates from the same session could both match at a
position (only possible if one is an exact substring of the other — not
expected in practice: FF1 outputs are effectively random within their
domain, and no name in `src/session/names.py`'s placeholder list is a
prefix of another), the longer one wins, mirroring
`src/detect/precedence.py`'s own same-kind tie-break rule.
"""

import re
from typing import Final

from src.core.exceptions import RehydrationError
from src.core.logging import get_gateway_logger, log_event, redact_safe
from src.core.types import CorrelationId, EntityType, Tier
from src.pipeline.field_walker import JSONValue, rebuild, walk
from src.session.known_surrogate import KnownSurrogate
from src.session.names import DEFAULT_NAME_CANDIDATES
from src.session.session import Session
from src.surrogate import engine, registry
from src.surrogate.key_provider import KeyProvider

_NAME_MAP_ENTITY_TYPES: Final[frozenset[EntityType]] = frozenset({"PERSON", "ORG", "ADDRESS"})
"""Entity types rehydrated via the session's name map
(`Session.lookup_real_name`), not FF1 decryption — mirrors
ARCHITECTURE.md's Surrogate Architecture split between fixed/finite
domains (stateless FF1) and the unbounded-domain names (session map)."""

REQUIRED_WINDOW_LOOKAHEAD: Final[int] = max(
    registry.max_registered_surrogate_length(),
    max(len(name) for name in DEFAULT_NAME_CANDIDATES),
)
"""The sliding window's lookahead margin for the response path — derived,
not guessed, from the longest surrogate this session could ever need to
rehydrate: the longest currently-registered FF1 domain output, or the
longest name in the current candidate list, whichever is longer.
Recomputed automatically (at import time) whenever either source
changes — there is no second, hand-copied number to fall out of sync.

Why no extra margin for decoration, contradicting ARCHITECTURE.md's
literal "longest entity... plus longest decoration" phrasing: that
formula is written for a matcher that has to account for decoration
characters appearing *between* an entity's own characters. This
engine's exact-substring matching never needs that — decoration wraps
*around* a surrogate's contiguous span (see the module docstring), so
the window only ever needs to hold one complete surrogate's own
characters at once, never the decoration around it too.
"""


def rehydrate(
    text: str,
    session: Session,
    key_provider: KeyProvider,
    *,
    correlation_id: CorrelationId,
) -> str:
    """Return `text` with every occurrence of a surrogate this session
    has minted replaced by its real value. Text containing no known
    surrogate is returned unchanged (the common case — most response
    text carries no PII at all).

    Intended to run as a `SlidingWindow`'s `transform` — see
    `sliding_window.py`'s module docstring for why it must be applied
    to the *entire* retained buffer, not to an already-released
    fragment, for a split surrogate to ever be caught whole.

    Raises:
        RehydrationError: a matched surrogate's recorded `entity_type`
            is a name-map type, but the session's reverse name map has
            no value for it — an invariant violation (see that
            exception's own docstring), not an ordinary miss.
        SurrogateDomainError: a matched surrogate's recorded
            `entity_type` has no registered FF1 domain (propagates from
            `engine.decrypt()` — not expected to occur in practice,
            since a surrogate is only ever recorded for a type that was
            already successfully encrypted on the request path).
    """
    known = session.known_surrogate_snapshot()
    if not known:
        return text

    logger = get_gateway_logger()

    def _replace(match: re.Match[str]) -> str:
        surrogate = match.group(0)
        record = known[surrogate]
        real_value = _resolve_real_value(surrogate, record.entity_type, session, key_provider)
        log_event(
            logger,
            "pipeline.surrogate_rehydrated",
            correlation_id=correlation_id,
            redacted=redact_safe(
                entity_type=record.entity_type,
                span_start=match.start(),
                span_end=match.end(),
                tier=_tier_for(record.entity_type),
                surrogate=surrogate,
            ),
        )
        return real_value

    return _pattern_for(known).sub(_replace, text)


def rehydrate_body(
    body: dict[str, JSONValue],
    session: Session,
    key_provider: KeyProvider,
    *,
    correlation_id: CorrelationId,
) -> dict[str, JSONValue]:
    """The non-streaming counterpart to `rehydrate()`: rehydrate every
    text-bearing field of a full (already-complete, non-streamed)
    response body, the same way `sanitize()` walks a request body.

    Reuses `field_walker.walk()`/`rebuild()` rather than special-casing
    `choices[].message.content` — a real upstream's response could carry
    text needing rehydration in more than one place (mirroring why the
    request-path walker is generic rather than a fixed field list), and
    the mechanism for "every text-bearing field, offset-safe rebuild" is
    the exact same one `sanitize()` already established; duplicating a
    second, content-only extractor for the response side would be new
    logic doing an already-solved job (CLAUDE.md: "no duplicated
    logic").
    """
    substitutions: dict[tuple[str | int, ...], str] = {}
    for region in walk(body):
        new_text = rehydrate(region.text, session, key_provider, correlation_id=correlation_id)
        if new_text != region.text:
            substitutions[region.path] = new_text

    result = rebuild(body, substitutions)
    rehydrated = result.body
    assert isinstance(rehydrated, dict), "rebuild() preserves a dict body's top-level type"
    return rehydrated


def _resolve_real_value(
    surrogate: str, entity_type: EntityType, session: Session, key_provider: KeyProvider
) -> str:
    if entity_type in _NAME_MAP_ENTITY_TYPES:
        real_value = session.lookup_real_name(surrogate)
        if real_value is None:
            raise RehydrationError(
                f"known-surrogate registry has entity_type={entity_type} (a name-map type) "
                "for a surrogate with no matching entry in this session's reverse name map"
            )
        return real_value
    return engine.decrypt(entity_type, surrogate, key_provider)


def _tier_for(entity_type: EntityType) -> Tier:
    """The tier that would have resolved `entity_type` on detection —
    derived, not stored: `KnownSurrogate` (Phase 3 Task 1) deliberately
    carries only `entity_type` and `created_at`, not the originating
    `Span`'s tier, so this mirrors `Span`'s own tier semantics (Tier 1 =
    checksum/regex structured types; Tier 2 = name-map types) rather
    than introducing a second, independently-set tier value that could
    drift from it."""
    return 2 if entity_type in _NAME_MAP_ENTITY_TYPES else 1


def _pattern_for(known: dict[str, KnownSurrogate]) -> re.Pattern[str]:
    """Build one alternation over every known surrogate, longest first.

    Longest-first ordering makes Python's `re` alternation (tries each
    branch left-to-right, first match wins at a given position) resolve
    the near-impossible case of one known surrogate being an exact
    substring of another in favour of the longer, more specific one —
    the same same-kind tie-break `precedence.py` already applies to
    Tier-1 detection, reused here for consistency rather than left
    undefined.
    """
    ordered = sorted(known, key=len, reverse=True)
    return re.compile("|".join(re.escape(surrogate) for surrogate in ordered))
