"""src.session.rng: the injectable RNG factory (Phase 4 Task 5)."""

import random

from src.session.rng import get_rng


def test_get_rng_returns_a_random_instance() -> None:
    assert isinstance(get_rng(), random.Random)


def test_get_rng_returns_a_fresh_instance_every_call() -> None:
    """Deliberately not cached (unlike get_key_provider()/
    get_session_store()/get_tier2_model()) — see the module's own
    docstring for the concurrency reasoning."""
    assert get_rng() is not get_rng()
