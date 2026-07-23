"""SessionStore: lifecycle only — create, look up, lazily evict and
replace. Session-state correctness (TTL refresh, the known-surrogate
registry) is tested directly on Session in test_session.py; these tests
are about the store's own responsibility: which Session object a
session_id currently maps to, and the two-lock protocol that must never
let unrelated sessions block on each other.
"""

import gc
import threading
import time
import weakref
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest

from src.core.types import SessionId
from src.session.store import SessionStore
from tests.conftest import FakeClock

_TTL = timedelta(seconds=30)


def test_get_or_create_creates_a_new_session_for_an_unseen_id(fake_clock: FakeClock) -> None:
    store = SessionStore(clock=fake_clock, ttl=_TTL)

    session = store.get_or_create(SessionId("s1"))

    assert session.session_id == "s1"


def test_get_or_create_returns_the_same_object_on_repeated_calls_within_ttl(
    fake_clock: FakeClock,
) -> None:
    store = SessionStore(clock=fake_clock, ttl=_TTL)

    first = store.get_or_create(SessionId("s1"))
    fake_clock.advance(timedelta(seconds=5))
    second = store.get_or_create(SessionId("s1"))

    assert first is second


def test_get_or_create_two_different_ids_get_independent_sessions(fake_clock: FakeClock) -> None:
    store = SessionStore(clock=fake_clock, ttl=_TTL)

    a = store.get_or_create(SessionId("a"))
    b = store.get_or_create(SessionId("b"))

    assert a is not b
    assert a.session_id != b.session_id


def test_sliding_ttl_repeated_access_before_expiry_keeps_a_session_alive_past_fixed_ttl(
    fake_clock: FakeClock,
) -> None:
    """Proves TTL is sliding, not fixed-from-creation: accessing every
    20s under a 30s TTL must never let the session expire, even well
    past 30s of total elapsed time since creation."""
    store = SessionStore(clock=fake_clock, ttl=_TTL)
    created = store.get_or_create(SessionId("s1"))

    for _ in range(5):
        fake_clock.advance(timedelta(seconds=20))
        touched = store.get_or_create(SessionId("s1"))
        assert touched is created

    # Total elapsed: 100s, far past a 30s fixed TTL, yet still the
    # original session.


def test_get_or_create_replaces_an_expired_session_with_a_fresh_empty_one(
    fake_clock: FakeClock,
) -> None:
    store = SessionStore(clock=fake_clock, ttl=_TTL)
    original = store.get_or_create(SessionId("s1"))
    original.record_surrogate("ABCDE1234F", "PAN", fake_clock.now())

    fake_clock.advance(_TTL + timedelta(seconds=1))
    replacement = store.get_or_create(SessionId("s1"))

    assert replacement is not original
    assert replacement.session_id == "s1"
    assert replacement.lookup_surrogate("ABCDE1234F") is None


def test_concurrent_get_or_create_on_one_new_id_never_creates_duplicates(
    fake_clock: FakeClock,
) -> None:
    """50 threads racing to create the same brand-new session: exactly
    one Session object must win, never one per thread."""
    store = SessionStore(clock=fake_clock, ttl=_TTL)

    with ThreadPoolExecutor(max_workers=50) as pool:
        results = list(pool.map(lambda _: store.get_or_create(SessionId("s1")), range(50)))

    assert len({id(session) for session in results}) == 1


def test_concurrent_get_or_create_across_many_ids_each_gets_its_own_session(
    fake_clock: FakeClock,
) -> None:
    store = SessionStore(clock=fake_clock, ttl=_TTL)
    ids = [SessionId(f"s{i}") for i in range(50)]

    with ThreadPoolExecutor(max_workers=50) as pool:
        sessions = list(pool.map(store.get_or_create, ids))

    assert len({s.session_id for s in sessions}) == 50


def test_get_or_create_does_not_serialize_across_different_sessions(fake_clock: FakeClock) -> None:
    """Concrete proof of the two-lock protocol's whole point: while one
    session is blocked deep inside its own (session-level) lock, a
    request on a *different* session must not wait for it — the store
    lock is only ever held for the O(1) dict lookup, never across a
    Session-level operation.
    """
    store = SessionStore(clock=fake_clock, ttl=_TTL)
    slow_session = store.get_or_create(SessionId("slow"))

    entered = threading.Event()
    release = threading.Event()
    real_touch_if_alive = slow_session.touch_if_alive

    def blocking_touch_if_alive(now: datetime, ttl: timedelta) -> bool:
        entered.set()
        release.wait(timeout=5)
        return real_touch_if_alive(now, ttl)

    slow_session.touch_if_alive = blocking_touch_if_alive  # type: ignore[method-assign]

    blocked = threading.Thread(target=lambda: store.get_or_create(SessionId("slow")))
    blocked.start()
    assert entered.wait(timeout=5), "the blocked call never entered touch_if_alive"

    try:
        start = time.monotonic()
        store.get_or_create(SessionId("fast"))
        elapsed = time.monotonic() - start
        assert elapsed < 1.0, (
            f"get_or_create('fast') took {elapsed:.3f}s while 'slow' was blocked — "
            "the store lock is being held across a Session-level operation"
        )
    finally:
        release.set()
        blocked.join(timeout=5)


def test_max_sessions_must_be_at_least_one(fake_clock: FakeClock) -> None:
    with pytest.raises(ValueError):
        SessionStore(clock=fake_clock, ttl=_TTL, max_sessions=0)


def test_capacity_cap_evicts_the_least_recently_used_session_when_exceeded(
    fake_clock: FakeClock,
) -> None:
    """Reaches into `_sessions` directly rather than calling
    `get_or_create()` again to check survivors: calling it again would
    itself be an access, perturbing the very LRU order under test."""
    store = SessionStore(clock=fake_clock, ttl=_TTL, max_sessions=2)
    store.get_or_create(SessionId("a"))
    store.get_or_create(SessionId("b"))

    store.get_or_create(SessionId("c"))  # exceeds capacity; "a" is LRU

    assert set(store._sessions.keys()) == {"b", "c"}


def test_accessing_a_session_updates_its_recency_and_it_survives_eviction(
    fake_clock: FakeClock,
) -> None:
    store = SessionStore(clock=fake_clock, ttl=_TTL, max_sessions=2)
    store.get_or_create(SessionId("a"))
    store.get_or_create(SessionId("b"))

    fake_clock.advance(timedelta(seconds=1))
    store.get_or_create(SessionId("a"))  # touch "a" again -> now most-recently-used

    store.get_or_create(SessionId("c"))  # exceeds capacity; "b" is now LRU, not "a"

    assert set(store._sessions.keys()) == {"a", "c"}


def test_replacing_an_expired_session_does_not_evict_an_unrelated_session(
    fake_clock: FakeClock,
) -> None:
    """Replacing an existing (expired) key must not count as store
    growth — it must never trigger a capacity eviction of some other,
    unrelated session."""
    store = SessionStore(clock=fake_clock, ttl=_TTL, max_sessions=2)
    store.get_or_create(SessionId("a"))
    store.get_or_create(SessionId("b"))

    fake_clock.advance(_TTL + timedelta(seconds=1))
    store.get_or_create(SessionId("a"))  # "a" expired; replaced in place

    assert set(store._sessions.keys()) == {"a", "b"}


def test_a_session_created_after_eviction_has_no_memory_of_the_evicted_ones_state(
    fake_clock: FakeClock,
) -> None:
    store = SessionStore(clock=fake_clock, ttl=_TTL, max_sessions=1)
    original = store.get_or_create(SessionId("a"))
    original.record_surrogate("ABCDE1234F", "PAN", fake_clock.now())

    store.get_or_create(SessionId("b"))  # evicts "a" under a 1-session cap
    recreated = store.get_or_create(SessionId("a"))  # "a" is gone; built fresh

    assert recreated is not original
    assert recreated.lookup_surrogate("ABCDE1234F") is None


def test_an_evicted_sessions_state_is_actually_garbage_collected(fake_clock: FakeClock) -> None:
    """Phase 7 session-lifecycle audit: goes one step further than the
    test above, which only proves the *store's* map no longer
    references the evicted Session. This proves the Session object
    itself is actually reclaimed, not merely unreachable through the
    store while still lingering somewhere else.

    `gc.collect()` is called explicitly before asserting. CPython's
    plain reference counting would already reclaim this object with no
    cyclic-GC pass at all — Session holds no reference cycle back to
    itself (its dicts and its lock hold nothing that points back to the
    Session instance) — but the test itself should not depend on that
    being the interpreter's particular memory model.
    """
    store = SessionStore(clock=fake_clock, ttl=_TTL, max_sessions=1)
    original = store.get_or_create(SessionId("a"))
    ref = weakref.ref(original)
    del original  # drop the one reference this test itself was holding

    store.get_or_create(SessionId("b"))  # evicts "a" under a 1-session cap
    gc.collect()

    assert ref() is None


def test_concurrent_get_or_create_never_exceeds_max_sessions_under_real_thread_load(
    fake_clock: FakeClock,
) -> None:
    """Phase 7 session-lifecycle audit: combines two properties this
    file otherwise tests separately — real thread concurrency (e.g.
    test_concurrent_get_or_create_on_one_new_id_never_creates_duplicates,
    above) and the capacity cap
    (test_capacity_cap_evicts_the_least_recently_used_session_when_exceeded,
    above) — to prove directly, under an actual race with far more
    threads than the cap, what get_or_create()'s single critical
    section already guarantees by construction: the store's size can
    never durably exceed max_sessions."""
    max_sessions = 10
    thread_count = 50
    store = SessionStore(clock=fake_clock, ttl=_TTL, max_sessions=max_sessions)
    ids = [SessionId(f"s{i}") for i in range(thread_count)]

    with ThreadPoolExecutor(max_workers=thread_count) as pool:
        list(pool.map(store.get_or_create, ids))

    assert len(store._sessions) <= max_sessions
