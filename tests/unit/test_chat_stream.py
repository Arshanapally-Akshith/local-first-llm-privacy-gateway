"""Tests for the OpenAI chat-completion-chunk parse/serialize layer."""

import json

import pytest

from src.core.exceptions import UpstreamError
from src.proxy.chat_stream import (
    ContentDelta,
    DoneMarker,
    parse_event,
    serialize_content_delta,
    serialize_done,
)
from src.proxy.sse_framing import SSEEvent

_ENVELOPE_COMMON = {
    "id": "chatcmpl-1",
    "object": "chat.completion.chunk",
    "created": 1,
    "model": "gpt-4",
}


def _content_event(content: str) -> SSEEvent:
    obj = {
        **_ENVELOPE_COMMON,
        "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
    }
    return SSEEvent(data=json.dumps(obj))


def _finish_event() -> SSEEvent:
    obj = {
        **_ENVELOPE_COMMON,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    return SSEEvent(data=json.dumps(obj))


def test_parse_event_extracts_content() -> None:
    result = parse_event(_content_event("hello"))

    assert isinstance(result, ContentDelta)
    assert result.content == "hello"


def test_parse_event_missing_content_field_yields_empty_string_not_an_error() -> None:
    result = parse_event(_finish_event())

    assert isinstance(result, ContentDelta)
    assert result.content == ""


def test_parse_event_recognizes_done_sentinel() -> None:
    result = parse_event(SSEEvent(data="[DONE]"))

    assert isinstance(result, DoneMarker)


def test_parse_event_rejects_invalid_json() -> None:
    with pytest.raises(UpstreamError) as exc_info:
        parse_event(SSEEvent(data="not json"))

    assert exc_info.value.status_code == 502


def test_parse_event_rejects_json_missing_choices() -> None:
    with pytest.raises(UpstreamError) as exc_info:
        parse_event(SSEEvent(data=json.dumps({"id": "x"})))

    assert exc_info.value.status_code == 502


def test_serialize_content_delta_round_trips_unchanged_content() -> None:
    delta = parse_event(_content_event("hello"))
    assert isinstance(delta, ContentDelta)

    line = serialize_content_delta(delta, "hello")

    assert line.startswith("data: ")
    assert line.endswith("\n\n")
    payload = json.loads(line[len("data: ") : -2])
    assert payload["choices"][0]["delta"]["content"] == "hello"
    assert payload["id"] == "chatcmpl-1"  # rest of the envelope preserved


def test_serialize_content_delta_substitutes_a_different_string() -> None:
    """Proves the seam Phase 3 needs: re-serializing with a DIFFERENT
    string than what was parsed, without this module changing."""
    delta = parse_event(_content_event("Arjun"))
    assert isinstance(delta, ContentDelta)

    line = serialize_content_delta(delta, "REDACTED")

    payload = json.loads(line[len("data: ") : -2])
    assert payload["choices"][0]["delta"]["content"] == "REDACTED"


def test_serialize_content_delta_does_not_invent_a_content_key() -> None:
    """The finish_reason chunk has no `content` key inside delta at
    all — serialization must not add one that was never there."""
    delta = parse_event(_finish_event())
    assert isinstance(delta, ContentDelta)

    line = serialize_content_delta(delta, "")

    payload = json.loads(line[len("data: ") : -2])
    assert "content" not in payload["choices"][0]["delta"]
    assert payload["choices"][0]["finish_reason"] == "stop"


def test_serialize_content_delta_does_not_mutate_the_original_envelope() -> None:
    delta = parse_event(_content_event("hello"))
    assert isinstance(delta, ContentDelta)
    original = dict(delta.envelope)

    serialize_content_delta(delta, "different")

    assert delta.envelope == original


def test_serialize_done() -> None:
    assert serialize_done() == "data: [DONE]\n\n"
