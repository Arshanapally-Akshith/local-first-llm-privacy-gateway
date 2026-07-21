"""Injected access to the current time — never `datetime.now()` called
inline in domain code (CLAUDE.md: "Anything with a clock... is
injected, never reached for globally"). This is what makes TTL expiry
testable deterministically, without sleeping — a test controls time by
constructing a fake `Clock`, not by waiting on the real one.

Lives in `core`, not `session`: nothing about "what time is it" is
session-specific, and `core` is the one layer every other layer can
already reach without exception (CLAUDE.md's layering: `proxy ->
pipeline -> detect/surrogate/session -> core`). Placing it in
`session` would make any future non-session component that also needs
time (e.g. a name-list exhaustion timestamp, or a future rate limiter)
import sideways across a sibling layer, which the frozen layering
diagram does not describe.
"""

from datetime import datetime, timezone
from functools import lru_cache
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Return the current time, timezone-aware (UTC).

        Must be pure and side-effect-free beyond reading the clock
        itself: same call, monotonically non-decreasing time — no
        caching, no mutation of caller state.
        """
        ...


class SystemClock:
    """`Clock` backed by the real wall clock. The only implementation
    that ever calls `datetime.now()` directly in this codebase."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@lru_cache
def get_clock() -> Clock:
    """FastAPI dependency: one `Clock` per process, mirroring
    `upstream_client.get_upstream_client()`'s exact shape. `SystemClock`
    is stateless, so caching buys nothing on its own, but sharing one
    instance keeps every caller — `SessionStore`, `sanitize()` — reading
    the same clock, and matches the DI pattern the rest of this codebase
    already uses consistently."""
    return SystemClock()
