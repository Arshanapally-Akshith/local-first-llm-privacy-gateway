"""pipeline.sanitize: proves the full request-path orchestration —
field walker + detection cascade + surrogate engine + session +
PII-safe logging — is wired together correctly. Each component already
has its own exhaustive unit tests; these prove end-to-end behavior
through `sanitize()` itself, including the field-coverage guarantee
(system prompt + tool-call arguments, Phase 2) and ingress-surrogate
recognition (Phase 3 Task 3: a known surrogate is never re-encrypted,
and a fresh substitution is recorded for future recognition).

`captured_records` and `fake_clock` are defined once in
tests/conftest.py and shared across the suite. `_sanitize()` supplies a
fixed `fail_mode="closed"` for every test that isn't specifically
exercising Phase 4 Task 4's FAIL_MODE gating, below.
"""

import json
import logging
import random

import pytest

from src.core.clock import Clock
from src.core.exceptions import SurrogateDomainError
from src.core.fail_mode import FailClosedError, FailMode
from src.core.logging import PiiSafeFormatter
from src.core.types import CorrelationId, EntityType, Offset, SessionId
from src.detect.tier1.checksum import verhoeff_generate_check_digit
from src.detect.tier2.model import ModelEntityMatch, Tier2Model
from src.pipeline.field_walker import JSONValue
from src.pipeline.sanitize import sanitize
from src.session.session import Session
from tests.conftest import FakeClock


class _FakeKeyProvider:
    def __init__(self, key: bytes) -> None:
        self._key = key

    def get_key(self) -> bytes:
        return self._key


class _FakeTier2Model:
    """A fixed set of matches, filtered to whichever ones actually fit
    the `text` a given call receives.

    Unlike `test_cascade.py`'s fake (called directly with one fixed
    `text`), this one is exercised through the full `sanitize()` ->
    `field_walker.walk()` pipeline, which calls `detect()` once per
    text-bearing field in the body — including fields like `model`
    ("gpt-4") that have nothing to do with the test's own scenario. A
    real model never returns offsets past the length of the text it was
    given; this fake must not either, or it fails
    `Tier2Detector.detect()`'s offset validation on every unrelated,
    shorter region.
    """

    def __init__(self, matches: list[ModelEntityMatch] | None = None) -> None:
        self._matches = matches if matches is not None else []

    def find_entities(self, text: str) -> list[ModelEntityMatch]:
        return [m for m in self._matches if m.end <= len(text)]


class _RaisingTier2Model:
    """A `Tier2Model` whose `find_entities()` always raises — the
    Phase 4 Task 4 "model unavailable" case, exercised end-to-end
    through `sanitize()` rather than just `cascade.detect()` directly
    (see `test_cascade.py` for the cascade-level equivalent)."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def find_entities(self, text: str) -> list[ModelEntityMatch]:
        raise self._exc


def _match(start: int, end: int, entity_type: EntityType) -> ModelEntityMatch:
    return ModelEntityMatch(start=Offset(start), end=Offset(end), entity_type=entity_type)


_KEY_PROVIDER = _FakeKeyProvider(b"k" * 32)
_CORRELATION_ID = CorrelationId("corr-test-1")
_NO_FINDINGS_MODEL: Tier2Model = _FakeTier2Model()

_PAYLOAD = "23456789012"
_VALID_AADHAAR = _PAYLOAD + verhoeff_generate_check_digit(_PAYLOAD)
_VALID_PAN = "AAAPL1234C"


def _fresh_session(clock: Clock) -> Session:
    return Session(SessionId("s1"), created_at=clock.now())


def _sanitize(
    body: dict[str, JSONValue],
    session: Session,
    clock: Clock,
    tier2_model: Tier2Model = _NO_FINDINGS_MODEL,
    fail_mode: FailMode = "closed",
) -> dict[str, JSONValue]:
    """`sanitize()`, with fixed `_KEY_PROVIDER`/`fail_mode`/
    `correlation_id` for every test that isn't specifically exercising
    Phase 4 Task 4's FAIL_MODE gating. `rng` is freshly seeded per call
    (not shared across calls) so tests allocating more than one name in
    the same session still see real, session-consistent collision
    behaviour rather than a single call's worth of shuffle state."""
    return sanitize(
        body,
        _KEY_PROVIDER,
        session,
        clock,
        tier2_model,
        fail_mode,
        random.Random(0),
        correlation_id=_CORRELATION_ID,
    )


def _first_message_content(body: dict[str, JSONValue]) -> str:
    """Extract `body["messages"][0]["content"]` as a real `str`.

    Every test in this file only ever inspects one message's `content`
    as a string — `sanitize()`'s own return type is `dict[str,
    JSONValue]` (correctly; a sanitized body can contain anything a
    request body can), so every test that wants to assert something
    string-specific about the result needs to narrow it first. One
    `isinstance`-checked helper here means every call site gets a real
    `str` back, instead of each repeating the same narrowing (or, worse,
    a blind `cast()` that would not actually catch a genuinely malformed
    result the way this assertion does).
    """
    messages = body["messages"]
    assert isinstance(messages, list)
    message = messages[0]
    assert isinstance(message, dict)
    content = message["content"]
    assert isinstance(content, str)
    return content


def _first_message_tool_call_arguments(body: dict[str, JSONValue]) -> str:
    """Extract `body["messages"][0]["tool_calls"][0]["function"]["arguments"]`
    as a real `str` — the one test in this file inspecting a tool-call
    argument string, narrowed the same way `_first_message_content()`
    narrows `content`."""
    messages = body["messages"]
    assert isinstance(messages, list)
    message = messages[0]
    assert isinstance(message, dict)
    tool_calls = message["tool_calls"]
    assert isinstance(tool_calls, list)
    tool_call = tool_calls[0]
    assert isinstance(tool_call, dict)
    function = tool_call["function"]
    assert isinstance(function, dict)
    arguments = function["arguments"]
    assert isinstance(arguments, str)
    return arguments


def test_no_pii_returns_a_structurally_equal_body(fake_clock: FakeClock) -> None:
    body: dict[str, JSONValue] = {"model": "gpt-4", "messages": [{"role": "user", "content": "hello there"}]}

    result = _sanitize(body, _fresh_session(fake_clock), fake_clock)

    assert result == body


def test_substitutes_a_single_entity_in_message_content(fake_clock: FakeClock) -> None:
    body: dict[str, JSONValue] = {
        "model": "gpt-4",
        "messages": [{"role": "user", "content": f"my Aadhaar is {_VALID_AADHAAR}"}],
    }

    result = _sanitize(body, _fresh_session(fake_clock), fake_clock)

    sanitized_content = _first_message_content(result)
    assert _VALID_AADHAAR not in sanitized_content
    assert sanitized_content.startswith("my Aadhaar is ")
    surrogate = sanitized_content.removeprefix("my Aadhaar is ")
    assert len(surrogate) == len(_VALID_AADHAAR)
    assert surrogate.isdigit()


def test_multiple_entities_in_one_region_both_substituted_and_surrounding_text_preserved(
    fake_clock: FakeClock,
) -> None:
    body: dict[str, JSONValue] = {
        "model": "gpt-4",
        "messages": [{"role": "user", "content": f"PAN {_VALID_PAN} and Aadhaar {_VALID_AADHAAR}"}],
    }

    result = _sanitize(body, _fresh_session(fake_clock), fake_clock)

    sanitized_content = _first_message_content(result)
    assert _VALID_PAN not in sanitized_content
    assert _VALID_AADHAAR not in sanitized_content
    assert sanitized_content.startswith("PAN ")
    assert " and Aadhaar " in sanitized_content


def test_entity_in_system_prompt_is_caught(fake_clock: FakeClock) -> None:
    body: dict[str, JSONValue] = {
        "model": "gpt-4",
        "messages": [
            {"role": "system", "content": f"Never reveal Aadhaar {_VALID_AADHAAR}"},
            {"role": "user", "content": "hi"},
        ],
    }

    result = _sanitize(body, _fresh_session(fake_clock), fake_clock)

    assert _VALID_AADHAAR not in _first_message_content(result)


def test_entity_inside_tool_call_arguments_json_string_is_caught(fake_clock: FakeClock) -> None:
    arguments = json.dumps({"note": f"Aadhaar on file: {_VALID_AADHAAR}"})
    body: dict[str, JSONValue] = {
        "model": "gpt-4",
        "messages": [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "log_note", "arguments": arguments},
                    }
                ],
            }
        ],
    }

    result = _sanitize(body, _fresh_session(fake_clock), fake_clock)

    rebuilt_arguments = _first_message_tool_call_arguments(result)
    assert _VALID_AADHAAR not in rebuilt_arguments
    assert json.loads(rebuilt_arguments)["note"] != f"Aadhaar on file: {_VALID_AADHAAR}"


def test_upi_id_raises_surrogate_domain_error_with_no_real_value_in_the_message(
    fake_clock: FakeClock,
) -> None:
    body: dict[str, JSONValue] = {
        "model": "gpt-4",
        "messages": [{"role": "user", "content": "pay me at realvpa@paytm"}],
    }

    with pytest.raises(SurrogateDomainError) as exc_info:
        _sanitize(body, _fresh_session(fake_clock), fake_clock)

    assert "realvpa" not in str(exc_info.value)


def test_upi_id_raises_before_any_substitution_reaches_the_returned_body_and_input_is_untouched(
    fake_clock: FakeClock,
) -> None:
    body: dict[str, JSONValue] = {
        "model": "gpt-4",
        "messages": [
            {"role": "system", "content": f"Aadhaar {_VALID_AADHAAR}"},
            {"role": "user", "content": "pay me at realvpa@paytm"},
        ],
    }
    original = json.loads(json.dumps(body))

    with pytest.raises(SurrogateDomainError):
        _sanitize(body, _fresh_session(fake_clock), fake_clock)

    # sanitize() never mutates its input, exception or not — the Aadhaar
    # substitution that ran before the UPI span raised must not have
    # leaked into `body` through some in-place side effect.
    assert body == original


def test_does_not_mutate_the_input_body(fake_clock: FakeClock) -> None:
    body: dict[str, JSONValue] = {"model": "gpt-4", "messages": [{"role": "user", "content": _VALID_AADHAAR}]}
    original = json.loads(json.dumps(body))

    _sanitize(body, _fresh_session(fake_clock), fake_clock)

    assert body == original


def test_logs_one_line_per_substituted_span_with_the_surrogate_never_the_real_value(
    fake_clock: FakeClock,
    captured_records: list[logging.LogRecord],
) -> None:
    body: dict[str, JSONValue] = {
        "model": "gpt-4",
        "messages": [{"role": "user", "content": f"Aadhaar {_VALID_AADHAAR}"}],
    }

    _sanitize(body, _fresh_session(fake_clock), fake_clock)

    formatter = PiiSafeFormatter()
    formatted = [json.loads(formatter.format(r)) for r in captured_records]
    span_lines = [f for f in formatted if f.get("event") == "pipeline.span_sanitized"]

    assert len(span_lines) == 1
    line = span_lines[0]
    assert line["entity_type"] == "AADHAAR"
    assert line["correlation_id"] == _CORRELATION_ID
    assert line["surrogate"] != _VALID_AADHAAR
    for f in formatted:
        assert _VALID_AADHAAR not in json.dumps(f)


def test_a_fresh_substitution_is_recorded_in_the_session_for_future_recognition(
    fake_clock: FakeClock,
) -> None:
    session = _fresh_session(fake_clock)
    body: dict[str, JSONValue] = {"model": "gpt-4", "messages": [{"role": "user", "content": _VALID_AADHAAR}]}

    result = _sanitize(body, session, fake_clock)

    surrogate = _first_message_content(result)
    record = session.lookup_surrogate(surrogate)
    assert record is not None
    assert record.entity_type == "AADHAAR"


def test_a_surrogate_already_known_to_the_session_is_passed_through_unchanged(
    fake_clock: FakeClock,
) -> None:
    """The Phase 3 Task 3 scenario: a value already recognised as a
    surrogate this session minted must never be re-encrypted."""
    session = _fresh_session(fake_clock)
    session.record_surrogate(_VALID_AADHAAR, "AADHAAR", fake_clock.now())
    body: dict[str, JSONValue] = {"model": "gpt-4", "messages": [{"role": "user", "content": f"Noted: {_VALID_AADHAAR}"}]}

    result = _sanitize(body, session, fake_clock)

    assert _first_message_content(result) == f"Noted: {_VALID_AADHAAR}"


def test_a_known_surrogate_alongside_a_new_entity_only_substitutes_the_new_one(
    fake_clock: FakeClock,
) -> None:
    session = _fresh_session(fake_clock)
    session.record_surrogate(_VALID_AADHAAR, "AADHAAR", fake_clock.now())
    body: dict[str, JSONValue] = {
        "model": "gpt-4",
        "messages": [
            {"role": "user", "content": f"Known {_VALID_AADHAAR} and new PAN {_VALID_PAN}"}
        ],
    }

    result = _sanitize(body, session, fake_clock)

    content = _first_message_content(result)
    assert f"Known {_VALID_AADHAAR}" in content  # untouched — already known
    assert _VALID_PAN not in content  # substituted — genuinely new


def test_a_region_with_only_a_known_surrogate_produces_no_log_line(
    fake_clock: FakeClock,
    captured_records: list[logging.LogRecord],
) -> None:
    """No substitution happened, so nothing should be logged as
    substituted — a pass-through span is not a "span_sanitized" event."""
    session = _fresh_session(fake_clock)
    session.record_surrogate(_VALID_AADHAAR, "AADHAAR", fake_clock.now())
    body: dict[str, JSONValue] = {"model": "gpt-4", "messages": [{"role": "user", "content": _VALID_AADHAAR}]}

    _sanitize(body, session, fake_clock)

    formatter = PiiSafeFormatter()
    formatted = [json.loads(formatter.format(r)) for r in captured_records]
    span_lines = [f for f in formatted if f.get("event") == "pipeline.span_sanitized"]
    assert span_lines == []


# --- Phase 4 Task 3: Tier-2 wired through sanitize() ------------------------


def test_tier1_wins_over_an_overlapping_tier2_span_end_to_end(fake_clock: FakeClock) -> None:
    """The BUILD.md gate scenario through the full `sanitize()`
    orchestration, not just `cascade.detect()` directly: a PAN embedded
    in a span Tier 2 calls ORG resolves as a PAN (Tier 1 wins the
    overlap), substituted with an FF1 surrogate — not the ORG name-map
    mechanism Task 5 wired in, since Tier 1 already claimed this exact
    span and precedence eliminates the overlapping ORG proposal
    entirely (`src/detect/precedence.py`)."""
    content = f"Please invoice {_VALID_PAN} Textiles Pvt Ltd"
    org_start = content.index(_VALID_PAN)
    model = _FakeTier2Model([_match(org_start, len(content), "ORG")])
    body: dict[str, JSONValue] = {"model": "gpt-4", "messages": [{"role": "user", "content": content}]}

    result = _sanitize(body, _fresh_session(fake_clock), fake_clock, model)

    sanitized_content = _first_message_content(result)
    assert _VALID_PAN not in sanitized_content
    assert sanitized_content.startswith("Please invoice ")
    assert sanitized_content.endswith(" Textiles Pvt Ltd")


# --- Phase 4 Task 5: PERSON/ORG/ADDRESS allocate real name-map surrogates ---


def test_a_detected_person_span_is_substituted_with_a_name_map_surrogate(
    fake_clock: FakeClock,
) -> None:
    """Closes Phase 4 Task 3's disclosed gap: a genuine Tier-2 PERSON
    detection no longer raises `SurrogateDomainError` — it is allocated
    a realistic "First Last" surrogate from `DEFAULT_NAME_CANDIDATES`
    via the session name map, exactly like a Phase 3 name allocation."""
    content = "Ramesh Kumar called yesterday"
    model = _FakeTier2Model([_match(0, len("Ramesh Kumar"), "PERSON")])
    body: dict[str, JSONValue] = {"model": "gpt-4", "messages": [{"role": "user", "content": content}]}

    result = _sanitize(body, _fresh_session(fake_clock), fake_clock, model)

    sanitized_content = _first_message_content(result)
    assert "Ramesh Kumar" not in sanitized_content
    assert sanitized_content.endswith(" called yesterday")
    surrogate = sanitized_content.removesuffix(" called yesterday")
    assert len(surrogate.split(" ")) == 2  # still "First Last" shaped


def test_org_and_address_spans_are_also_substituted_via_the_name_map(
    fake_clock: FakeClock,
) -> None:
    """The scope decision behind this task: all three Tier-2 types, not
    PERSON alone, get real surrogates."""
    content = "Contact Bharat Textiles at 12 MG Road, Bengaluru today"
    org_start = content.index("Bharat Textiles")
    org_end = org_start + len("Bharat Textiles")
    address_start = content.index("12 MG Road, Bengaluru")
    address_end = address_start + len("12 MG Road, Bengaluru")
    model = _FakeTier2Model(
        [_match(org_start, org_end, "ORG"), _match(address_start, address_end, "ADDRESS")]
    )
    body: dict[str, JSONValue] = {"model": "gpt-4", "messages": [{"role": "user", "content": content}]}

    result = _sanitize(body, _fresh_session(fake_clock), fake_clock, model)

    sanitized_content = _first_message_content(result)
    assert "Bharat Textiles" not in sanitized_content
    assert "12 MG Road, Bengaluru" not in sanitized_content
    assert sanitized_content.startswith("Contact ")
    assert sanitized_content.endswith(" today")


def test_the_same_real_name_gets_the_same_surrogate_within_one_session(
    fake_clock: FakeClock,
) -> None:
    """Session-consistency (ARCHITECTURE.md: "consistent by
    construction"), proven for the name-map path across two separate
    `sanitize()` calls on the same session — the FF1 side gets this for
    free from statelessness; the name-map side gets it from
    `Session.allocate_or_lookup_name()`'s idempotent forward map."""
    session = _fresh_session(fake_clock)
    model = _FakeTier2Model([_match(0, len("Ramesh Kumar"), "PERSON")])
    body_1: dict[str, JSONValue] = {"model": "gpt-4", "messages": [{"role": "user", "content": "Ramesh Kumar called"}]}
    body_2: dict[str, JSONValue] = {"model": "gpt-4", "messages": [{"role": "user", "content": "Ramesh Kumar emailed"}]}

    result_1 = _sanitize(body_1, session, fake_clock, model)
    result_2 = _sanitize(body_2, session, fake_clock, model)

    surrogate_1 = _first_message_content(result_1).removesuffix(" called")
    surrogate_2 = _first_message_content(result_2).removesuffix(" emailed")
    assert surrogate_1 == surrogate_2


# --- Phase 4 Task 4: Tier-2 failures are gated by FAIL_MODE -----------------


def test_tier2_failure_with_fail_mode_open_still_sanitizes_tier1_entities(
    fake_clock: FakeClock,
    captured_records: list[logging.LogRecord],
) -> None:
    """The model itself failing must not take down Tier-1 sanitization
    with it: under `open`, the Aadhaar is still substituted, and the
    Tier-2 failure is logged rather than silently swallowed."""
    body: dict[str, JSONValue] = {
        "model": "gpt-4",
        "messages": [{"role": "user", "content": f"Aadhaar {_VALID_AADHAAR}"}],
    }
    model = _RaisingTier2Model(RuntimeError("model process crashed"))

    result = _sanitize(body, _fresh_session(fake_clock), fake_clock, model, "open")

    sanitized_content = _first_message_content(result)
    assert _VALID_AADHAAR not in sanitized_content
    formatter = PiiSafeFormatter()
    events = [json.loads(formatter.format(r))["event"] for r in captured_records]
    assert "detection.tier2_failed" in events


def test_tier2_failure_with_fail_mode_closed_raises_fail_closed_error_and_body_untouched(
    fake_clock: FakeClock,
) -> None:
    body: dict[str, JSONValue] = {
        "model": "gpt-4",
        "messages": [{"role": "user", "content": f"Aadhaar {_VALID_AADHAAR}"}],
    }
    original = json.loads(json.dumps(body))
    model = _RaisingTier2Model(RuntimeError("model process crashed"))

    with pytest.raises(FailClosedError):
        _sanitize(body, _fresh_session(fake_clock), fake_clock, model, "closed")

    assert body == original
