"""Injectable RNG for Tier-2 name-map allocation (Phase 4 Task 5).

`Session.allocate_or_lookup_name()` requires a `random.Random` instance,
injected (CLAUDE.md: "the RNG... injected, never reached for globally").
"""

import random


def get_rng() -> random.Random:
    """Return a fresh `random.Random` instance.

    Deliberately **not** `@lru_cache`d like `get_key_provider()`/
    `get_session_store()`/`get_tier2_model()`: those cache a genuinely
    expensive-to-construct or genuinely-must-be-shared resource. A
    single shared `random.Random` instance reused across concurrent
    requests on *different* sessions would be a real thread-safety bug
    — `Session.allocate_or_lookup_name()`'s own lock only serialises
    access to *that one session's* state, not to a globally shared RNG
    object two different sessions' concurrent calls could both be
    mutating at once, since `random.Random`'s methods are not
    thread-safe against concurrent callers. Constructing a fresh,
    unseeded instance per call sidesteps the concurrency question
    entirely, at effectively zero cost, rather than introducing a lock
    this project's threading model doesn't otherwise need.
    """
    return random.Random()
