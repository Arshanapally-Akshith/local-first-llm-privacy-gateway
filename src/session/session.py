"""One conversation's session-scoped state.

`Session` owns *behaviour* — every read or write of its own state goes
through a method that already holds its own lock. `SessionStore` owns
*lifecycle* only (create, look up, evict) and never reaches into a
`Session`'s internals directly (Phase 3 architectural decision: "Keep
SessionStore intentionally small... avoid convenience APIs that
duplicate Session functionality").

`threading.Lock`, not `asyncio.Lock`: every method here is a handful of
dict/attribute operations with no `await` and no I/O, so the critical
section is microseconds regardless of primitive. A plain `threading.Lock`
is the primitive that is actually correct if request handling ever runs
this code from a worker thread (FastAPI/Starlette can do this for sync
dependencies), not just from concurrent async tasks on one event loop —
an `asyncio.Lock` only ever protects the latter. BUILD.md's Phase 3 DoD
says "thread-safe," not "coroutine-safe," and this is the primitive that
actually delivers that.
"""

import random
import threading
from collections.abc import Sequence
from datetime import datetime, timedelta

from src.core.exceptions import NameListExhaustedError
from src.core.types import EntityType, SessionId
from src.session.known_surrogate import KnownSurrogate


class Session:
    """Session-scoped state for one conversation: when it was last
    used, which surrogate values it has minted so far, and — for
    Tier-2 (unbounded-domain) entities — the bidirectional real-value
    <-> surrogate-name map ARCHITECTURE.md's Surrogate Architecture
    describes as the one piece of state FF1 never needed.

    Every method below acquires `self._lock` directly; none call each
    other while already holding it (`threading.Lock` is not
    reentrant — a method calling another locked method on `self` from
    inside its own `with self._lock:` block would deadlock). Where a
    name allocation also needs to update the known-surrogate registry,
    it writes to `_known_surrogates` directly rather than calling
    `record_surrogate()`, for exactly this reason.
    """

    def __init__(self, session_id: SessionId, created_at: datetime) -> None:
        self.session_id = session_id
        """Immutable once set; never reassigned after construction, so
        reading it needs no lock."""

        self._lock = threading.Lock()
        self._last_accessed_at = created_at
        self._known_surrogates: dict[str, KnownSurrogate] = {}
        self._name_forward: dict[str, str] = {}
        """real name -> surrogate name. The one place in this system a
        real value is ever held in a map at all (ARCHITECTURE.md:
        structured entities need none; names unavoidably do). Never
        logged, never exposed by any method that doesn't require the
        caller to already know the real value being looked up."""
        self._name_reverse: dict[str, str] = {}
        """surrogate name -> real name. Rehydration's counterpart to
        `_name_forward` — same real-value-holding sensitivity."""

    def touch_if_alive(self, now: datetime, ttl: timedelta) -> bool:
        """Atomically check TTL expiry and, if still alive, refresh it
        (sliding TTL — Phase 3 architectural decision: activity extends
        a session's life, rather than a fixed lifetime from creation).

        Check-then-update happens under one lock acquisition
        deliberately: reading `last_accessed_at`, comparing it to `now`,
        and conditionally writing a new value are three steps that must
        not be visible as separate operations to a concurrent caller,
        or two racing calls could each decide "still alive" against a
        now-stale timestamp and then stomp each other's refresh.

        Args:
            now: the current time, from the caller's injected `Clock`
                — this method never reads a clock itself (CLAUDE.md:
                inject the clock; `Session` holds no `Clock` reference
                at all, by design — see the class docstring).
            ttl: the configured session TTL. Owned and supplied by
                `SessionStore` (the lifecycle policy holder), not
                stored on `Session` itself — a session does not know
                its own TTL, only when it was last touched.

        Returns:
            `True` and refreshes `last_accessed_at` to `now` if the
            elapsed time since the last access is within `ttl`.
            `False`, unchanged, if the session has expired — the
            caller (`SessionStore`) is responsible for deciding what
            happens next (BUILD.md: lazy eviction — nothing evicts a
            session except a future access that finds it expired).
        """
        with self._lock:
            if now - self._last_accessed_at > ttl:
                return False
            self._last_accessed_at = now
            return True

    def record_surrogate(self, surrogate: str, entity_type: EntityType, now: datetime) -> None:
        """Record that this session has minted `surrogate` for
        `entity_type`, so a later request replaying it can be
        recognised instead of re-encrypted (Phase 3 Task 3, not yet
        built).

        Never stores the real value `surrogate` was derived from —
        only the surrogate itself and its type. Recording the same
        surrogate string twice overwrites the earlier metadata; nothing
        currently depends on the first-seen timestamp surviving a
        second substitution of the same value.
        """
        with self._lock:
            self._known_surrogates[surrogate] = KnownSurrogate(
                entity_type=entity_type, created_at=now
            )

    def lookup_surrogate(self, surrogate: str) -> KnownSurrogate | None:
        """Return this session's record for `surrogate`, or `None` if
        this session never minted it.

        Exact string match only — no normalisation, no fuzzy matching.
        Conservative-matching is an architectural decision (a
        rehydration oracle otherwise — see ARCHITECTURE.md, Response
        Lifecycle), not merely a Task 1 simplification.
        """
        with self._lock:
            return self._known_surrogates.get(surrogate)

    def allocate_or_lookup_name(
        self,
        real_value: str,
        entity_type: EntityType,
        candidates: Sequence[str],
        rng: random.Random,
        now: datetime,
    ) -> str:
        """Return this session's surrogate for `real_value`, allocating
        one from `candidates` if this is the first time this session
        has seen it.

        The whole operation — check-existing, shuffle, probe for an
        unused candidate, commit — happens under one lock acquisition,
        deliberately: splitting "is this candidate free" and "claim it"
        into two separately-locked calls would let two concurrent
        callers both see the same candidate as free and both claim it,
        producing exactly the collision BUILD.md's Phase 3 DoD forbids
        ("two in-flight requests assigning a surrogate to the same new
        name must not produce two mappings" generalises to: two real
        values must never end up sharing one surrogate name).

        Idempotent per real value: calling this again for the same
        `real_value` within the same session always returns the same
        surrogate, without consuming any of `rng`'s state or touching
        `candidates` again — consistent with ARCHITECTURE.md's
        "consistent by construction" property structured entities get
        for free from FF1, reproduced here for names by an explicit
        forward-map check first.

        `candidates` is copied before shuffling — `rng.shuffle()` is
        in-place, and mutating a caller-supplied sequence as a side
        effect of a lookup would be surprising. A successful new
        allocation also records a `KnownSurrogate` entry (Task 1's
        registry), so Task 3's ingress recognition works identically
        for name surrogates and Tier-1 surrogates, through one shared
        mechanism rather than two.

        Args:
            real_value: the real name (or org, or address — any
                Tier-2 entity's real text) this call is allocating a
                surrogate for.
            entity_type: recorded on the resulting `KnownSurrogate`
                entry; not otherwise used by this method.
            candidates: the name pool to allocate from. Not owned or
                cached by `Session` — the caller supplies the same
                pool on every call, so which pool is in play is never
                implicit.
            rng: injected, never a module-level `random.shuffle` call
                (CLAUDE.md: "the RNG... injected, never reached for
                globally"). `random.Random` itself, not a custom
                protocol — already fully deterministic when
                constructed with a fixed seed, so a bespoke test double
                buys nothing a seeded instance doesn't already give.
            now: this allocation's timestamp, for the `KnownSurrogate`
                entry — see `record_surrogate()`'s docstring for why
                `Session` takes this as a parameter rather than holding
                its own `Clock`.

        Raises:
            NameListExhaustedError: every candidate in `candidates` is
                already assigned to a *different* real value within
                this session.
        """
        with self._lock:
            # `real_value` alone is the identity key here — `entity_type`
            # is recorded on the resulting KnownSurrogate below but never
            # checked against a *prior* allocation for this same string.
            # If the same real_value is ever submitted twice with two
            # different entity_types, this silently returns the first
            # call's surrogate and type. An intentional Phase 3
            # simplification, not an oversight — this case is reachable
            # for real as of Phase 4 Task 5 (real PERSON/ORG/ADDRESS
            # detection is wired to this method), not merely hypothetical
            # anymore, but no failure from it has been observed or
            # reported. Revisit if it ever manifests as a real bug (e.g.
            # a string GLiNER tags ORG in one message and ADDRESS in
            # another, within the same session) rather than fixing it
            # speculatively now against a case that may never occur in
            # practice.
            existing = self._name_forward.get(real_value)
            if existing is not None:
                return existing

            shuffled = list(candidates)
            rng.shuffle(shuffled)
            for candidate in shuffled:
                if candidate not in self._name_reverse:
                    self._name_forward[real_value] = candidate
                    self._name_reverse[candidate] = real_value
                    self._known_surrogates[candidate] = KnownSurrogate(
                        entity_type=entity_type, created_at=now
                    )
                    return candidate

            raise NameListExhaustedError(
                f"no unused name available for entity_type={entity_type}: "
                f"{len(self._name_reverse)} of {len(candidates)} candidates "
                "already assigned in this session"
            )

    def known_surrogate_snapshot(self) -> dict[str, KnownSurrogate]:
        """Return a point-in-time copy of every surrogate this session
        has minted so far (both Tier-1 FF1 surrogates and Tier-2 name
        surrogates, recorded through one shared registry — see
        `docs/DECISIONS.md`), for the rehydration engine
        (`src/pipeline/rehydrate.py`) to build a match pattern from.

        A copy, not a live view: the caller builds a regex over the
        returned keys and scans a whole buffered chunk of response text
        with it, entirely outside this session's lock — the same
        "release the lock before doing the real work" discipline
        `SessionStore.get_or_create()` already applies (see
        `store.py`'s module docstring). A surrogate minted by a
        *different*, concurrent request on this same session after this
        snapshot was taken simply isn't considered by *this* rehydration
        call — an acceptable, momentary blind spot (the next buffered
        chunk's scan picks up any new mapping), not a correctness bug:
        nothing here promises atomicity between minting and rehydrating
        across two different requests.

        Safe to return without a deeper copy: `KnownSurrogate` is a
        frozen dataclass, so a caller holding this snapshot cannot
        mutate any entry through it even though the entries themselves
        are shared, not deep-copied.
        """
        with self._lock:
            return dict(self._known_surrogates)

    def lookup_real_name(self, surrogate: str) -> str | None:
        """Return the real value `surrogate` was allocated for, or
        `None` if this session never allocated it.

        The rehydration-side counterpart to `allocate_or_lookup_name()`
        — Tier-2's equivalent of `engine.decrypt()`, since names have
        no stateless inverse and must be looked up. Exact match only,
        same conservative-matching rationale as `lookup_surrogate()`.

        Returns `None`, not an error, for a surrogate this session
        never minted (including a Tier-1 surrogate, which is never
        present in this map at all) — an unresolvable surrogate is
        Task 4's expected, measured "miss" outcome, not this method's
        concern to distinguish from any other kind of absence.
        """
        with self._lock:
            return self._name_reverse.get(surrogate)
