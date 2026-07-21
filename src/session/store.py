"""The session registry: owns *lifecycle* only (create, look up,
evict-and-replace). All actual session state and its locking lives on
`Session` itself (see `session.py`'s module docstring) — this module
does not read or write a `Session`'s internals, only decide which
`Session` object a `session_id` currently maps to.

Two independent locks are involved, by design, and are never held
together:

- `SessionStore`'s own lock protects only the ordered `SessionId ->
  Session` map itself — insertion, lookup, replacement, LRU-order
  bookkeeping. Held for a handful of O(1) dict operations, nothing
  else.
- Each `Session`'s own lock (entirely private to that `Session`,
  never touched from here) protects that session's actual state.

The store lock is never held while a `Session`'s own lock-protected
method runs, and vice versa: `get_or_create()` always releases the
store lock before calling `Session.touch_if_alive()`. This is what
keeps a burst of concurrent requests on *different* sessions from ever
serialising behind each other's session-level work.
"""

import threading
from collections import OrderedDict
from datetime import timedelta
from functools import lru_cache

from src.core.clock import Clock, get_clock
from src.core.config import get_settings
from src.core.types import SessionId
from src.session.session import Session

DEFAULT_MAX_SESSIONS = 10_000
"""Guess, not a measurement — revisit once real session-churn numbers
exist. Chosen as generously large for this project's stated deployment
target (ARCHITECTURE.md: one developer's machine, not a fleet) while
still bounding the worst case: unlimited unique, never-revisited
session ids (an attacker, or simply many one-shot callers) would
otherwise grow `SessionStore` without limit, since lazy eviction only
ever fires on a *future* access to the same id — see
docs/DECISIONS.md, 2026-07-21, "Bounding session-store growth."
"""


class SessionStore:
    """Creates and looks up `Session`s, evicting expired ones lazily,
    and bounding total memory with a hard capacity cap.

    Lazy TTL eviction only, per the Phase 3 architectural decision: no
    background sweeper, timer, or cleanup thread exists or is planned.
    A session is checked for expiry, and replaced if expired, only at
    the moment `get_or_create()` is next called for its id — an
    abandoned session that nothing ever looks up again is never swept
    *by TTL*.

    That gap is bounded a different way: once `max_sessions` distinct
    sessions exist, creating one more evicts the least-recently-used
    entry first — deterministic, synchronous, triggered only by a real
    `get_or_create()` call, never a background process. See
    docs/DECISIONS.md, 2026-07-21, "Bounding session-store growth," for
    why a hard capacity cap was chosen over leaving unlimited unique-id
    growth as a documented-only limitation.

    **Two `Session` objects can transiently exist for one `SessionId`.**
    Both TTL expiry-and-replacement and LRU capacity eviction can cause
    `session_id`'s entry in `_sessions` to move on to a different
    `Session` object while a caller that fetched the *previous* object
    (before it was replaced or evicted) is still holding and using it —
    an in-flight request never has its reference invalidated out from
    under it mid-call. This is an accepted, intentional invariant, not
    an oversight: see docs/DECISIONS.md, 2026-07-21, "Two Session
    objects for one SessionId," for why it introduces no data race and
    is functionally identical to the replacement behaviour this class
    already has purely from TTL expiry, with or without a capacity cap.
    """

    def __init__(
        self, clock: Clock, ttl: timedelta, max_sessions: int = DEFAULT_MAX_SESSIONS
    ) -> None:
        if max_sessions < 1:
            raise ValueError(f"max_sessions must be >= 1, got {max_sessions}")
        self._clock = clock
        self._ttl = ttl
        self._max_sessions = max_sessions
        self._lock = threading.Lock()
        self._sessions: OrderedDict[SessionId, Session] = OrderedDict()

    def get_or_create(self, session_id: SessionId) -> Session:
        """Return the live `Session` for `session_id`.

        Three outcomes, all handled here: the session exists and is
        still alive (fast path — refreshed and returned without a
        second lock acquisition); the session exists but has expired
        (replaced in place, which never counts against `max_sessions`
        — replacing an existing key does not grow the store); or the
        id has never been seen (created, evicting the
        least-recently-used entry first if the store is already at
        capacity).

        Always succeeds and always returns a usable session — there is
        no "session not found" or "session expired" outcome visible to
        the caller. Lazy eviction means this method cannot distinguish
        "this id has never been seen" from "this id existed and
        expired" — both produce an identical fresh, empty session, and
        nothing in this module needs that distinction (see
        `src/core/exceptions.py`'s note on `SessionExpiredError`).
        """
        now = self._clock.now()

        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                self._sessions.move_to_end(session_id)
        # Store lock released above before touching session state —
        # `touch_if_alive` acquires `session`'s own lock, never the
        # store's.
        if session is not None and session.touch_if_alive(now, self._ttl):
            return session

        with self._lock:
            # Re-check under the lock: either another concurrent caller
            # already replaced an expired entry (or created a brand-new
            # one) while we were outside the lock above, or nothing has
            # changed and we need to do that replacement/creation
            # ourselves.
            current = self._sessions.get(session_id)
            if current is not None and current is not session:
                self._sessions.move_to_end(session_id)
                return current

            if session_id not in self._sessions and len(self._sessions) >= self._max_sessions:
                # Growing the store past capacity: evict the least-
                # recently-used entry first. Never reached when merely
                # replacing an existing (expired) key in place, since
                # that does not increase the session count.
                self._sessions.popitem(last=False)

            fresh = Session(session_id, created_at=now)
            self._sessions[session_id] = fresh
            self._sessions.move_to_end(session_id)
            return fresh


@lru_cache
def get_session_store() -> SessionStore:
    """FastAPI dependency: **one** `SessionStore` shared for the whole
    process, not one per request — unlike `get_upstream_client()` (a
    connection pool, cached purely for reuse), this caching is load-
    bearing for correctness: sessions must persist *across* requests to
    mean anything at all. A fresh, uncached `SessionStore` per request
    would make every request its own, empty session, defeating the
    entire point of Phase 3."""
    settings = get_settings()
    return SessionStore(clock=get_clock(), ttl=timedelta(seconds=settings.session_ttl))
