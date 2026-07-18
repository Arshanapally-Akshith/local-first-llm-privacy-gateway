"""Integration tests for the standalone mock upstream app.

Exercises it directly via TestClient (not through the gateway proxy,
which doesn't exist until Task 4), proving the mock itself is
OpenAI-shaped and honours pathological chunking directives.
"""

import json
from typing import Any

from fastapi.testclient import TestClient

from src.mock_upstream.main import app

client = TestClient(app)


def _parse_sse_events(raw: str) -> list[dict[str, Any] | None]:
    """Parse `data: ...` lines into JSON objects; `[DONE]` becomes None.

    Untyped values (Any) deliberately: this parses dynamic JSON test
    output, not domain data — a precise type here would just produce
    type: ignore comments at every assertion below with no real safety
    benefit.
    """
    events: list[dict[str, Any] | None] = []
    for line in raw.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[len("data: ") :]
        events.append(None if payload == "[DONE]" else json.loads(payload))
    return events


def test_streaming_echoes_last_message_content_by_default() -> None:
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "Hello world"}],
            "stream": True,
        },
    )

    assert response.status_code == 200
    events = _parse_sse_events(response.text)

    assert events[-1] is None  # terminated with [DONE]
    content_pieces = [
        e["choices"][0]["delta"].get("content", "") for e in events[:-1] if e is not None
    ]
    assert "".join(content_pieces) == "Hello world"


def test_streaming_honours_chunking_directive() -> None:
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "ABCDE1234F"}],
            "stream": True,
            "chunking": {"n": 5},
        },
    )

    events = _parse_sse_events(response.text)
    content_pieces = [
        e["choices"][0]["delta"].get("content", "") for e in events[:-1] if e is not None
    ]

    assert "".join(content_pieces) == "ABCDE1234F"
    # role-establishing chunk + 5 content chunks + final finish_reason chunk
    assert len(events) - 1 == 1 + 5 + 1


def test_streaming_chunking_directive_produces_zero_content_chunks() -> None:
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "ab"}],
            "stream": True,
            "chunking": {"n": 5},
        },
    )

    events = _parse_sse_events(response.text)
    content_deltas = [
        e["choices"][0]["delta"]["content"]
        for e in events[:-1]
        if e is not None and "content" in e["choices"][0]["delta"]
    ]

    assert "" in content_deltas


def test_streaming_terminates_with_done() -> None:
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        },
    )

    assert response.text.rstrip().endswith("data: [DONE]")


def test_non_streaming_echoes_last_message_content() -> None:
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "Hello world"}],
            "stream": False,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["choices"][0]["message"]["content"] == "Hello world"
    assert body["choices"][0]["finish_reason"] == "stop"


def test_non_streaming_is_the_default_when_stream_omitted() -> None:
    response = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 200
    assert response.json()["object"] == "chat.completion"


def test_tolerates_unmodelled_real_sdk_fields() -> None:
    """A real openai SDK call sends many fields the mock doesn't model
    (temperature, top_p, tools, ...). These must not cause a 422."""
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "hi"}],
            "temperature": 0.7,
            "top_p": 1.0,
            "tools": [],
            "user": "test-user",
        },
    )

    assert response.status_code == 200
