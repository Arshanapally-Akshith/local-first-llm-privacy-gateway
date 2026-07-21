"""Session: TTL refresh semantics and the known-surrogate registry.

Uses the shared `FakeClock` (tests/conftest.py) — TTL behaviour is
tested by moving a controlled clock forward, never by sleeping.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from src.core.types import EntityType, SessionId
from src.session.session import Session
from tests.conftest import FakeClock

_TTL = timedelta(seconds=30)


def _session(clock: FakeClock) -> Session:
    return Session(SessionId("s1"), created_at=clock.now())


def test_touch_if_alive_within_ttl_returns_true_and_refreshes(fake_clock: FakeClock) -> None:
    session = _session(fake_clock)
    fake_clock.advance(timedelta(seconds=10))

    assert session.touch_if_alive(fake_clock.now(), _TTL) is True

    # Refreshed: another 25s (past the *original* creation + 30s, but
    # well within 25s of the just-refreshed access) must still be alive.
    fake_clock.advance(timedelta(seconds=25))
    assert session.touch_if_alive(fake_clock.now(), _TTL) is True


def test_touch_if_alive_beyond_ttl_returns_false_and_does_not_refresh(
    fake_clock: FakeClock,
) -> None:
    session = _session(fake_clock)
    fake_clock.advance(timedelta(seconds=31))

    assert session.touch_if_alive(fake_clock.now(), _TTL) is False

    # A failed touch must not have refreshed last_accessed_at: checking
    # again from the same (still-expired) point must still say False,
    # not accidentally "come back to life" from the failed attempt.
    assert session.touch_if_alive(fake_clock.now(), _TTL) is False


def test_touch_if_alive_exactly_at_ttl_boundary_is_still_alive(fake_clock: FakeClock) -> None:
    """Off-by-one check: elapsed == ttl is not yet expired, only
    elapsed > ttl is. `>` vs `>=` is exactly the class of boundary
    CLAUDE.md flags as needing an explicit test, not an assumption."""
    session = _session(fake_clock)
    fake_clock.advance(_TTL)

    assert session.touch_if_alive(fake_clock.now(), _TTL) is True


def test_lookup_unknown_surrogate_returns_none(fake_clock: FakeClock) -> None:
    session = _session(fake_clock)

    assert session.lookup_surrogate("ABCDE1234F") is None


def test_record_then_lookup_surrogate_round_trips(fake_clock: FakeClock) -> None:
    session = _session(fake_clock)

    session.record_surrogate("ABCDE1234F", "PAN", fake_clock.now())
    record = session.lookup_surrogate("ABCDE1234F")

    assert record is not None
    assert record.entity_type == "PAN"
    assert record.created_at == fake_clock.now()


def test_record_surrogate_never_stores_a_real_value_field() -> None:
    """The KnownSurrogate record has no field capable of holding a real
    value at all — this test exists to fail loudly if that ever
    changes (CLAUDE.md: no PII at rest, ever)."""
    from dataclasses import fields

    from src.session.known_surrogate import KnownSurrogate

    field_names = {f.name for f in fields(KnownSurrogate)}
    assert field_names == {"entity_type", "created_at"}


def test_recording_the_same_surrogate_twice_overwrites_metadata(fake_clock: FakeClock) -> None:
    session = _session(fake_clock)
    session.record_surrogate("ABCDE1234F", "PAN", fake_clock.now())

    fake_clock.advance(timedelta(seconds=5))
    session.record_surrogate("ABCDE1234F", "PAN", fake_clock.now())

    record = session.lookup_surrogate("ABCDE1234F")
    assert record is not None
    assert record.created_at == fake_clock.now()


def test_known_surrogate_snapshot_reflects_recorded_surrogates(fake_clock: FakeClock) -> None:
    session = _session(fake_clock)
    session.record_surrogate("ABCDE1234F", "PAN", fake_clock.now())

    snapshot = session.known_surrogate_snapshot()

    assert set(snapshot) == {"ABCDE1234F"}
    assert snapshot["ABCDE1234F"].entity_type == "PAN"


def test_known_surrogate_snapshot_on_an_empty_session_is_an_empty_dict(
    fake_clock: FakeClock,
) -> None:
    session = _session(fake_clock)

    assert session.known_surrogate_snapshot() == {}


def test_known_surrogate_snapshot_is_a_copy_not_a_live_view(fake_clock: FakeClock) -> None:
    session = _session(fake_clock)
    session.record_surrogate("ABCDE1234F", "PAN", fake_clock.now())

    snapshot = session.known_surrogate_snapshot()
    snapshot["INJECTED"] = snapshot["ABCDE1234F"]

    assert session.lookup_surrogate("INJECTED") is None


def test_concurrent_record_surrogate_calls_lose_nothing(fake_clock: FakeClock) -> None:
    """50 threads, 50 distinct surrogates, one session: every write
    must survive. This is the Session-level half of BUILD.md's Phase 3
    concurrency DoD item; the full-stack, HTTP-level version belongs to
    the final integration task."""
    session = _session(fake_clock)
    surrogates = [f"SURR{i:04d}" for i in range(50)]
    entity_type: EntityType = "PAN"

    with ThreadPoolExecutor(max_workers=50) as pool:
        list(
            pool.map(
                lambda s: session.record_surrogate(s, entity_type, fake_clock.now()),
                surrogates,
            )
        )

    for surrogate in surrogates:
        record = session.lookup_surrogate(surrogate)
        assert record is not None
        assert record.entity_type == "PAN"
