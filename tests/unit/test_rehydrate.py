"""rehydrate() / rehydrate_body(): the response-path counterpart to
sanitize() — exact-match substitution of every surrogate a session has
minted, back to its real value.
"""

import random

import pytest

from src.core.exceptions import RehydrationError
from src.core.types import CorrelationId, EntityType, SessionId
from src.detect.tier1.checksum import verhoeff_generate_check_digit
from src.pipeline.rehydrate import REQUIRED_WINDOW_LOOKAHEAD, rehydrate, rehydrate_body
from src.session.names import DEFAULT_NAME_CANDIDATES
from src.session.session import Session
from src.surrogate import engine, registry
from tests.conftest import FakeClock

_PERSON: EntityType = "PERSON"
_CORRELATION_ID = CorrelationId("test-correlation-id")


class _FakeKeyProvider:
    def __init__(self, key: bytes = b"k" * 32) -> None:
        self._key = key

    def get_key(self) -> bytes:
        return self._key


class _IdentityShuffleRandom(random.Random):
    """A `random.Random` whose `shuffle()` is a no-op — mirrors
    `test_session_names.py`'s own helper. Duplicated locally rather than
    imported cross-module: a two-line test double belongs with the test
    that uses it, not shared production code (CLAUDE.md's "no
    duplicated logic" targets domain logic, not test fixtures)."""

    def shuffle(self, x: object, *args: object, **kwargs: object) -> None:  # type: ignore[override]
        return None


_KEY_PROVIDER = _FakeKeyProvider()
_AADHAAR_PAYLOAD = "23456789012"
_VALID_AADHAAR = _AADHAAR_PAYLOAD + verhoeff_generate_check_digit(_AADHAAR_PAYLOAD)


def _session(clock: FakeClock) -> Session:
    return Session(SessionId("s1"), created_at=clock.now())


def test_no_known_surrogates_returns_text_unchanged(fake_clock: FakeClock) -> None:
    session = _session(fake_clock)

    assert rehydrate("nothing to see here", session, _KEY_PROVIDER, correlation_id=_CORRELATION_ID) == (
        "nothing to see here"
    )


def test_rehydrates_a_structured_ff1_surrogate_to_its_real_value(fake_clock: FakeClock) -> None:
    session = _session(fake_clock)
    surrogate = engine.encrypt("AADHAAR", _VALID_AADHAAR, _KEY_PROVIDER)
    session.record_surrogate(surrogate, "AADHAAR", fake_clock.now())

    text = f"Your Aadhaar {surrogate} was approved"

    result = rehydrate(text, session, _KEY_PROVIDER, correlation_id=_CORRELATION_ID)

    assert result == f"Your Aadhaar {_VALID_AADHAAR} was approved"


def test_rehydrates_a_surrogate_wrapped_in_markdown_decoration(fake_clock: FakeClock) -> None:
    """Decoration wraps around the surrogate's own contiguous
    characters; exact substring matching catches it without any
    decoration-specific handling (see rehydrate.py's module
    docstring)."""
    session = _session(fake_clock)
    surrogate = engine.encrypt("AADHAAR", _VALID_AADHAAR, _KEY_PROVIDER)
    session.record_surrogate(surrogate, "AADHAAR", fake_clock.now())

    text = f"approved: **{surrogate}**"

    result = rehydrate(text, session, _KEY_PROVIDER, correlation_id=_CORRELATION_ID)

    assert result == f"approved: **{_VALID_AADHAAR}**"


def test_a_surrogate_shaped_string_this_session_never_minted_is_left_unchanged(
    fake_clock: FakeClock,
) -> None:
    """Conservative, session-scoped matching: a value that merely looks
    like a valid surrogate is not decrypted-and-substituted just
    because it satisfies the domain's shape — only strings *this
    session's own registry* actually recorded are matched."""
    session = _session(fake_clock)
    some_other_sessions_surrogate = engine.encrypt("AADHAAR", _VALID_AADHAAR, _KEY_PROVIDER)
    text = f"Aadhaar on file: {some_other_sessions_surrogate}"

    result = rehydrate(text, session, _KEY_PROVIDER, correlation_id=_CORRELATION_ID)

    assert result == text


def test_rehydrates_multiple_distinct_surrogates_in_one_text(fake_clock: FakeClock) -> None:
    session = _session(fake_clock)
    aadhaar_surrogate = engine.encrypt("AADHAAR", _VALID_AADHAAR, _KEY_PROVIDER)
    session.record_surrogate(aadhaar_surrogate, "AADHAAR", fake_clock.now())
    pan_real = "AAAPL1234C"
    pan_surrogate = engine.encrypt("PAN", pan_real, _KEY_PROVIDER)
    session.record_surrogate(pan_surrogate, "PAN", fake_clock.now())

    text = f"Aadhaar {aadhaar_surrogate}, PAN {pan_surrogate}"

    result = rehydrate(text, session, _KEY_PROVIDER, correlation_id=_CORRELATION_ID)

    assert result == f"Aadhaar {_VALID_AADHAAR}, PAN {pan_real}"


def test_rehydrates_a_name_map_surrogate_via_the_session_name_map(fake_clock: FakeClock) -> None:
    session = _session(fake_clock)
    surrogate = session.allocate_or_lookup_name(
        "Ramesh Kumar", _PERSON, list(DEFAULT_NAME_CANDIDATES), random.Random(1), fake_clock.now()
    )

    text = f"Noted, {surrogate}."

    result = rehydrate(text, session, _KEY_PROVIDER, correlation_id=_CORRELATION_ID)

    assert result == "Noted, Ramesh Kumar."


def test_name_map_entry_with_no_reverse_mapping_raises_rehydration_error(
    fake_clock: FakeClock,
) -> None:
    """`record_surrogate()` alone (unlike `allocate_or_lookup_name()`)
    never writes the reverse name map — deliberately constructing the
    invariant-violation state `RehydrationError` exists to catch,
    through the same public API a real drift would have to occur
    through."""
    session = _session(fake_clock)
    session.record_surrogate("Someone Nobody Allocated", _PERSON, fake_clock.now())

    with pytest.raises(RehydrationError, match="PERSON"):
        rehydrate(
            "Noted, Someone Nobody Allocated.",
            session,
            _KEY_PROVIDER,
            correlation_id=_CORRELATION_ID,
        )


def test_longest_known_surrogate_wins_when_one_is_a_substring_of_another(
    fake_clock: FakeClock,
) -> None:
    session = _session(fake_clock)
    rng = _IdentityShuffleRandom()
    # Identity shuffle + this candidate order: "Ann" allocated first (to
    # real_a), "Ann Marie" second (to real_b) -- "Ann" is a substring of
    # "Ann Marie", the near-impossible collision _pattern_for's
    # longest-first ordering exists to resolve deterministically.
    session.allocate_or_lookup_name("Real A", _PERSON, ["Ann", "Ann Marie"], rng, fake_clock.now())
    session.allocate_or_lookup_name("Real B", _PERSON, ["Ann", "Ann Marie"], rng, fake_clock.now())

    result = rehydrate("Hello, Ann Marie!", session, _KEY_PROVIDER, correlation_id=_CORRELATION_ID)

    assert result == "Hello, Real B!"


def test_rehydrate_body_walks_every_text_bearing_field(fake_clock: FakeClock) -> None:
    session = _session(fake_clock)
    surrogate = engine.encrypt("AADHAAR", _VALID_AADHAAR, _KEY_PROVIDER)
    session.record_surrogate(surrogate, "AADHAAR", fake_clock.now())
    body = {
        "id": "chatcmpl-1",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": f"Aadhaar: {surrogate}"},
                "finish_reason": "stop",
            }
        ],
    }

    result = rehydrate_body(body, session, _KEY_PROVIDER, correlation_id=_CORRELATION_ID)

    assert result["choices"][0]["message"]["content"] == f"Aadhaar: {_VALID_AADHAAR}"  # type: ignore[index]
    assert result["id"] == "chatcmpl-1"


def test_rehydrate_body_leaves_a_body_with_nothing_to_rehydrate_unchanged(
    fake_clock: FakeClock,
) -> None:
    session = _session(fake_clock)
    body = {"choices": [{"message": {"content": "Hello world"}}]}

    result = rehydrate_body(body, session, _KEY_PROVIDER, correlation_id=_CORRELATION_ID)

    assert result == body


def test_required_window_lookahead_covers_every_registered_domain_and_name() -> None:
    assert REQUIRED_WINDOW_LOOKAHEAD >= registry.max_registered_surrogate_length()
    assert REQUIRED_WINDOW_LOOKAHEAD >= max(len(name) for name in DEFAULT_NAME_CANDIDATES)
