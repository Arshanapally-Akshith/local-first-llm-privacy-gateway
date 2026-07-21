"""Session.allocate_or_lookup_name() / lookup_real_name(): the Tier-2
name allocator, its collision handling, and its exhaustion failure
mode — BUILD.md's Phase 3 DoD: "Collision handling at assignment time
... test with a forced-tiny name list to make collisions certain" and
"50 parallel requests on one session, no duplicate/lost mappings."
"""

import random
from concurrent.futures import ThreadPoolExecutor

import pytest

from src.core.exceptions import NameListExhaustedError
from src.core.types import EntityType, SessionId
from src.session.session import Session
from tests.conftest import FakeClock

_PERSON: EntityType = "PERSON"


class _IdentityShuffleRandom(random.Random):
    """A `random.Random` whose `shuffle()` is a no-op — every call sees
    candidates in the exact order given. This is what makes the
    collision-*handling* code path directly, deterministically
    provable: with a real shuffle, two allocations might simply never
    pick the same first candidate by chance, and the retry-on-collision
    logic would never actually run during the test."""

    def shuffle(self, x: object, *args: object, **kwargs: object) -> None:  # type: ignore[override]
        return None


def _session(clock: FakeClock) -> Session:
    return Session(SessionId("s1"), created_at=clock.now())


def test_allocates_a_candidate_for_a_new_real_value(fake_clock: FakeClock) -> None:
    session = _session(fake_clock)

    surrogate = session.allocate_or_lookup_name(
        "Ramesh Kumar",
        _PERSON,
        ["Aarav Sharma", "Vivaan Gupta"],
        random.Random(1),
        fake_clock.now(),
    )

    assert surrogate in ("Aarav Sharma", "Vivaan Gupta")


def test_allocation_is_idempotent_for_the_same_real_value(fake_clock: FakeClock) -> None:
    session = _session(fake_clock)
    candidates = ["Aarav Sharma", "Vivaan Gupta", "Aditya Verma"]

    first = session.allocate_or_lookup_name(
        "Ramesh Kumar", _PERSON, candidates, random.Random(1), fake_clock.now()
    )
    second = session.allocate_or_lookup_name(
        "Ramesh Kumar", _PERSON, candidates, random.Random(2), fake_clock.now()
    )

    assert first == second


def test_different_real_values_get_different_surrogates(fake_clock: FakeClock) -> None:
    session = _session(fake_clock)
    candidates = ["Aarav Sharma", "Vivaan Gupta", "Aditya Verma"]

    a = session.allocate_or_lookup_name(
        "Ramesh Kumar", _PERSON, candidates, random.Random(1), fake_clock.now()
    )
    b = session.allocate_or_lookup_name(
        "Suresh Iyer", _PERSON, candidates, random.Random(1), fake_clock.now()
    )

    assert a != b


def test_collision_forced_tiny_list_no_two_real_values_ever_share_a_surrogate(
    fake_clock: FakeClock,
) -> None:
    """The literal BUILD.md scenario: a 3-name list, 3 distinct real
    values. An identity-shuffle RNG means every call's *preferred*
    order is identical — proving the surrogate assigned to each is
    only distinct because the collision-retry logic actually skips
    already-taken candidates, not because chance gave them different
    first picks."""
    session = _session(fake_clock)
    candidates = ["Aarav Sharma", "Vivaan Gupta", "Aditya Verma"]
    rng = _IdentityShuffleRandom()

    a = session.allocate_or_lookup_name("Ramesh Kumar", _PERSON, candidates, rng, fake_clock.now())
    b = session.allocate_or_lookup_name("Suresh Iyer", _PERSON, candidates, rng, fake_clock.now())
    c = session.allocate_or_lookup_name("Priya Nair", _PERSON, candidates, rng, fake_clock.now())

    assert {a, b, c} == set(candidates)  # all three distinct, all three candidates used


def test_exhaustion_raises_once_every_candidate_is_assigned_to_a_different_value(
    fake_clock: FakeClock,
) -> None:
    session = _session(fake_clock)
    candidates = ["Aarav Sharma", "Vivaan Gupta"]
    rng = _IdentityShuffleRandom()
    session.allocate_or_lookup_name("Ramesh Kumar", _PERSON, candidates, rng, fake_clock.now())
    session.allocate_or_lookup_name("Suresh Iyer", _PERSON, candidates, rng, fake_clock.now())

    with pytest.raises(NameListExhaustedError):
        session.allocate_or_lookup_name("Priya Nair", _PERSON, candidates, rng, fake_clock.now())


def test_exhaustion_error_message_never_contains_the_real_value(fake_clock: FakeClock) -> None:
    session = _session(fake_clock)
    candidates = ["Aarav Sharma"]
    rng = _IdentityShuffleRandom()
    session.allocate_or_lookup_name("Ramesh Kumar", _PERSON, candidates, rng, fake_clock.now())

    with pytest.raises(NameListExhaustedError) as exc_info:
        session.allocate_or_lookup_name(
            "a-secret-real-name", _PERSON, candidates, rng, fake_clock.now()
        )

    assert "a-secret-real-name" not in str(exc_info.value)


def test_exhaustion_does_not_prevent_looking_up_an_already_allocated_value(
    fake_clock: FakeClock,
) -> None:
    """Exhaustion only applies to *new* real values — a value already
    mapped must keep resolving via the idempotent fast path even once
    the list is fully spoken for."""
    session = _session(fake_clock)
    candidates = ["Aarav Sharma"]
    rng = _IdentityShuffleRandom()
    surrogate = session.allocate_or_lookup_name(
        "Ramesh Kumar", _PERSON, candidates, rng, fake_clock.now()
    )

    again = session.allocate_or_lookup_name(
        "Ramesh Kumar", _PERSON, candidates, rng, fake_clock.now()
    )

    assert again == surrogate


def test_does_not_mutate_the_caller_supplied_candidates_list(fake_clock: FakeClock) -> None:
    session = _session(fake_clock)
    candidates = ["Aarav Sharma", "Vivaan Gupta", "Aditya Verma"]
    original = list(candidates)

    session.allocate_or_lookup_name(
        "Ramesh Kumar", _PERSON, candidates, random.Random(1), fake_clock.now()
    )

    assert candidates == original


def test_a_new_allocation_is_recorded_as_a_known_surrogate(fake_clock: FakeClock) -> None:
    """Task 3's ingress recognition must work uniformly for name
    surrogates and Tier-1 surrogates — proven here by checking the
    same registry Task 1 built."""
    session = _session(fake_clock)
    candidates = ["Aarav Sharma", "Vivaan Gupta"]

    surrogate = session.allocate_or_lookup_name(
        "Ramesh Kumar", _PERSON, candidates, random.Random(1), fake_clock.now()
    )

    record = session.lookup_surrogate(surrogate)
    assert record is not None
    assert record.entity_type == "PERSON"


def test_lookup_real_name_round_trips_after_allocation(fake_clock: FakeClock) -> None:
    session = _session(fake_clock)
    candidates = ["Aarav Sharma", "Vivaan Gupta"]

    surrogate = session.allocate_or_lookup_name(
        "Ramesh Kumar", _PERSON, candidates, random.Random(1), fake_clock.now()
    )

    assert session.lookup_real_name(surrogate) == "Ramesh Kumar"


def test_lookup_real_name_returns_none_for_an_unknown_surrogate(fake_clock: FakeClock) -> None:
    session = _session(fake_clock)

    assert session.lookup_real_name("Someone Nobody Allocated") is None


def test_concurrent_allocation_of_the_same_real_value_produces_one_shared_surrogate(
    fake_clock: FakeClock,
) -> None:
    """BUILD.md, Phase 3: 'two in-flight requests assigning a
    surrogate to the same new name must not produce two mappings.'"""
    session = _session(fake_clock)
    candidates = [f"Candidate{i}" for i in range(100)]

    with ThreadPoolExecutor(max_workers=50) as pool:
        results = list(
            pool.map(
                lambda _: session.allocate_or_lookup_name(
                    "Ramesh Kumar", _PERSON, candidates, random.Random(), fake_clock.now()
                ),
                range(50),
            )
        )

    assert len(set(results)) == 1


def test_concurrent_allocation_of_distinct_real_values_loses_nothing_and_collides_nothing(
    fake_clock: FakeClock,
) -> None:
    """The full DoD statement, generalised across many distinct
    values: 50 threads, 50 distinct real values, one session — every
    surrogate must be distinct and every value must resolve back
    correctly afterwards."""
    session = _session(fake_clock)
    candidates = [f"Candidate{i}" for i in range(100)]
    real_values = [f"RealPerson{i}" for i in range(50)]

    with ThreadPoolExecutor(max_workers=50) as pool:
        surrogates = list(
            pool.map(
                lambda real_value: session.allocate_or_lookup_name(
                    real_value, _PERSON, candidates, random.Random(), fake_clock.now()
                ),
                real_values,
            )
        )

    assert len(set(surrogates)) == 50  # no two real values collided onto one surrogate
    for real_value, surrogate in zip(real_values, surrogates, strict=True):
        assert session.lookup_real_name(surrogate) == real_value
