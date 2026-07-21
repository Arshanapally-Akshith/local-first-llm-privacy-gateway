"""Typed exception hierarchy for the gateway.

Callers catch categories (GatewayError subclasses), never strings.
Every message states what failed and what to do about it — never a
sensitive value (CLAUDE.md, Error Handling). Children are added only
once a phase actually raises them, not ahead of need.
"""


class GatewayError(Exception):
    """Root of the gateway's exception hierarchy. Never raised directly."""


class UpstreamError(GatewayError):
    """The configured upstream (mock or live) could not be reached, timed
    out, or returned something the proxy cannot treat as a valid
    response.

    Carries the HTTP status the proxy should return to its own caller,
    decided by whoever raises this (the upstream client). This class
    does not itself encode connection-failure-vs-timeout as separate
    subclasses — that would force every catch site to enumerate them
    instead of reading one field.
    """

    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class SurrogateDomainError(GatewayError):
    """A value cannot be represented in its entity type's FF1 domain —
    e.g. a span whose length the domain doesn't expect, or a value
    containing a character outside the domain's alphabet.

    Never caught to fall back to a pass-through: CLAUDE.md's Error
    Handling is explicit that a surrogate domain mismatch must raise,
    never silently emit the real value. The message states what
    failed and the expected shape — never the real value itself
    (CLAUDE.md: "no sensitive values in the message").
    """


class NameListExhaustedError(GatewayError):
    """A session has already assigned every candidate name in the list
    it was given, and needs one more for a real value it has never
    seen before.

    Named as a real failure mode in ARCHITECTURE.md's Name Allocator
    component ("Exhaustion — more distinct entities in a session than
    names in the list"), unlike `SessionExpiredError` below: this one
    has an immediate, real caller — `Session.allocate_or_lookup_name()`
    (Phase 3 Task 2) — and a test that genuinely exhausts a
    forced-tiny candidate list to exercise it, not a speculative one
    added ahead of need.

    The message states counts only (how many candidates, how many
    already assigned) — never the real value that triggered it.
    """


class RehydrationError(GatewayError):
    """A session's known-surrogate registry says a given surrogate's
    `entity_type` is a name-map type (`PERSON`/`ORG`/`ADDRESS`), but the
    session's own reverse name map has no real value recorded for it.

    This is an invariant violation, not an expected "miss":
    `Session.allocate_or_lookup_name()` (Phase 3 Task 2) always writes
    both the known-surrogate registry and the reverse name map for a
    name surrogate in the same locked operation
    (`src/session/session.py`), so a name-type entry with no matching
    reverse-map entry means those two maps have drifted apart — which
    should be impossible under the current code path, and must raise
    rather than silently guess. An unresolvable surrogate this session
    genuinely never minted (an ordinary "miss", per ARCHITECTURE.md's
    conservative-matching tradeoff) is a different case entirely and is
    never routed through this exception — it is simply left
    unsubstituted (see `src/pipeline/rehydrate.py`).

    The message states the entity type only — never the surrogate
    string or any real value (CLAUDE.md: "no sensitive values in the
    message").
    """


# SessionExpiredError intentionally does not exist yet, despite being
# named in CLAUDE.md's exception hierarchy and ARCHITECTURE.md's
# rehydration failure modes. It was added in Phase 3 Task 1 ahead of
# any real caller, then removed on review: SessionStore's lazy
# eviction always transparently returns a valid session, so nothing in
# Task 1 or Task 2 can actually raise it. CLAUDE.md's own rule —
# "Children are added only once a phase actually raises them, not
# ahead of need" — applies as written; see docs/DECISIONS.md,
# 2026-07-21, for the reversal. ARCHITECTURE.md's Rehydration Engine
# failure mode ("Expiry mid-conversation -> surrogates arrive back
# with no mapping -> SessionExpiredError") names its most likely real
# home: Phase 3 Task 4, if rehydration turns out to genuinely need to
# distinguish "this session expired" from an ordinary unresolvable
# surrogate. It may also turn out not to need the distinction at all,
# in which case this type stays absent.
