"""pipeline.sanitize: proves the full request-path orchestration —
field walker + detection cascade + surrogate engine + session +
PII-safe logging — is wired together correctly. Each component already
has its own exhaustive unit tests; these prove end-to-end behavior
through `sanitize()` itself, including the field-coverage guarantee
(system prompt + tool-call arguments, Phase 2) and ingress-surrogate
recognition (Phase 3 Task 3: a known surrogate is never re-encrypted,
and a fresh substitution is recorded for future recognition).

`captured_records` and `fake_clock` are defined once in
tests/conftest.py and shared across the suite.
"""

import json
import logging

import pytest

from src.core.clock import Clock
from src.core.exceptions import SurrogateDomainError
from src.core.logging import PiiSafeFormatter
from src.core.types import CorrelationId, SessionId
from src.detect.tier1.checksum import verhoeff_generate_check_digit
from src.pipeline.sanitize import sanitize
from src.session.session import Session
from tests.conftest import FakeClock


class _FakeKeyProvider:
    def __init__(self, key: bytes) -> None:
        self._key = key

    def get_key(self) -> bytes:
        return self._key


_KEY_PROVIDER = _FakeKeyProvider(b"k" * 32)
_CORRELATION_ID = CorrelationId("corr-test-1")

_PAYLOAD = "23456789012"
_VALID_AADHAAR = _PAYLOAD + verhoeff_generate_check_digit(_PAYLOAD)
_VALID_PAN = "AAAPL1234C"


def _fresh_session(clock: Clock) -> Session:
    return Session(SessionId("s1"), created_at=clock.now())


def test_no_pii_returns_a_structurally_equal_body(fake_clock: FakeClock) -> None:
    body = {"model": "gpt-4", "messages": [{"role": "user", "content": "hello there"}]}

    result = sanitize(
        body, _KEY_PROVIDER, _fresh_session(fake_clock), fake_clock, correlation_id=_CORRELATION_ID
    )

    assert result == body


def test_substitutes_a_single_entity_in_message_content(fake_clock: FakeClock) -> None:
    body = {
        "model": "gpt-4",
        "messages": [{"role": "user", "content": f"my Aadhaar is {_VALID_AADHAAR}"}],
    }

    result = sanitize(
        body, _KEY_PROVIDER, _fresh_session(fake_clock), fake_clock, correlation_id=_CORRELATION_ID
    )

    sanitized_content = result["messages"][0]["content"]
    assert _VALID_AADHAAR not in sanitized_content
    assert sanitized_content.startswith("my Aadhaar is ")
    surrogate = sanitized_content.removeprefix("my Aadhaar is ")
    assert len(surrogate) == len(_VALID_AADHAAR)
    assert surrogate.isdigit()


def test_multiple_entities_in_one_region_both_substituted_and_surrounding_text_preserved(
    fake_clock: FakeClock,
) -> None:
    body = {
        "model": "gpt-4",
        "messages": [{"role": "user", "content": f"PAN {_VALID_PAN} and Aadhaar {_VALID_AADHAAR}"}],
    }

    result = sanitize(
        body, _KEY_PROVIDER, _fresh_session(fake_clock), fake_clock, correlation_id=_CORRELATION_ID
    )

    sanitized_content = result["messages"][0]["content"]
    assert _VALID_PAN not in sanitized_content
    assert _VALID_AADHAAR not in sanitized_content
    assert sanitized_content.startswith("PAN ")
    assert " and Aadhaar " in sanitized_content


def test_entity_in_system_prompt_is_caught(fake_clock: FakeClock) -> None:
    body = {
        "model": "gpt-4",
        "messages": [
            {"role": "system", "content": f"Never reveal Aadhaar {_VALID_AADHAAR}"},
            {"role": "user", "content": "hi"},
        ],
    }

    result = sanitize(
        body, _KEY_PROVIDER, _fresh_session(fake_clock), fake_clock, correlation_id=_CORRELATION_ID
    )

    assert _VALID_AADHAAR not in result["messages"][0]["content"]


def test_entity_inside_tool_call_arguments_json_string_is_caught(fake_clock: FakeClock) -> None:
    arguments = json.dumps({"note": f"Aadhaar on file: {_VALID_AADHAAR}"})
    body = {
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

    result = sanitize(
        body, _KEY_PROVIDER, _fresh_session(fake_clock), fake_clock, correlation_id=_CORRELATION_ID
    )

    rebuilt_arguments = result["messages"][0]["tool_calls"][0]["function"]["arguments"]
    assert _VALID_AADHAAR not in rebuilt_arguments
    assert json.loads(rebuilt_arguments)["note"] != f"Aadhaar on file: {_VALID_AADHAAR}"


def test_upi_id_raises_surrogate_domain_error_with_no_real_value_in_the_message(
    fake_clock: FakeClock,
) -> None:
    body = {
        "model": "gpt-4",
        "messages": [{"role": "user", "content": "pay me at realvpa@paytm"}],
    }

    with pytest.raises(SurrogateDomainError) as exc_info:
        sanitize(
            body,
            _KEY_PROVIDER,
            _fresh_session(fake_clock),
            fake_clock,
            correlation_id=_CORRELATION_ID,
        )

    assert "realvpa" not in str(exc_info.value)


def test_upi_id_raises_before_any_substitution_reaches_the_returned_body_and_input_is_untouched(
    fake_clock: FakeClock,
) -> None:
    body = {
        "model": "gpt-4",
        "messages": [
            {"role": "system", "content": f"Aadhaar {_VALID_AADHAAR}"},
            {"role": "user", "content": "pay me at realvpa@paytm"},
        ],
    }
    original = json.loads(json.dumps(body))

    with pytest.raises(SurrogateDomainError):
        sanitize(
            body,
            _KEY_PROVIDER,
            _fresh_session(fake_clock),
            fake_clock,
            correlation_id=_CORRELATION_ID,
        )

    # sanitize() never mutates its input, exception or not — the Aadhaar
    # substitution that ran before the UPI span raised must not have
    # leaked into `body` through some in-place side effect.
    assert body == original


def test_does_not_mutate_the_input_body(fake_clock: FakeClock) -> None:
    body = {"model": "gpt-4", "messages": [{"role": "user", "content": _VALID_AADHAAR}]}
    original = json.loads(json.dumps(body))

    sanitize(
        body, _KEY_PROVIDER, _fresh_session(fake_clock), fake_clock, correlation_id=_CORRELATION_ID
    )

    assert body == original


def test_logs_one_line_per_substituted_span_with_the_surrogate_never_the_real_value(
    fake_clock: FakeClock,
    captured_records: list[logging.LogRecord],
) -> None:
    body = {
        "model": "gpt-4",
        "messages": [{"role": "user", "content": f"Aadhaar {_VALID_AADHAAR}"}],
    }

    sanitize(
        body, _KEY_PROVIDER, _fresh_session(fake_clock), fake_clock, correlation_id=_CORRELATION_ID
    )

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
    body = {"model": "gpt-4", "messages": [{"role": "user", "content": _VALID_AADHAAR}]}

    result = sanitize(body, _KEY_PROVIDER, session, fake_clock, correlation_id=_CORRELATION_ID)

    surrogate = result["messages"][0]["content"]
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
    body = {"model": "gpt-4", "messages": [{"role": "user", "content": f"Noted: {_VALID_AADHAAR}"}]}

    result = sanitize(body, _KEY_PROVIDER, session, fake_clock, correlation_id=_CORRELATION_ID)

    assert result["messages"][0]["content"] == f"Noted: {_VALID_AADHAAR}"


def test_a_known_surrogate_alongside_a_new_entity_only_substitutes_the_new_one(
    fake_clock: FakeClock,
) -> None:
    session = _fresh_session(fake_clock)
    session.record_surrogate(_VALID_AADHAAR, "AADHAAR", fake_clock.now())
    body = {
        "model": "gpt-4",
        "messages": [
            {"role": "user", "content": f"Known {_VALID_AADHAAR} and new PAN {_VALID_PAN}"}
        ],
    }

    result = sanitize(body, _KEY_PROVIDER, session, fake_clock, correlation_id=_CORRELATION_ID)

    content = result["messages"][0]["content"]
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
    body = {"model": "gpt-4", "messages": [{"role": "user", "content": _VALID_AADHAAR}]}

    sanitize(body, _KEY_PROVIDER, session, fake_clock, correlation_id=_CORRELATION_ID)

    formatter = PiiSafeFormatter()
    formatted = [json.loads(formatter.format(r)) for r in captured_records]
    span_lines = [f for f in formatted if f.get("event") == "pipeline.span_sanitized"]
    assert span_lines == []
