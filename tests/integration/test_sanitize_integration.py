"""End-to-end proof of the Phase 2 gate (BUILD.md): a real-format
Aadhaar and PAN placed in a tool definition — not the user message —
must never reach the upstream in plaintext. Routes through the real
`app`, the real `sanitize()` pipeline, and the real mock upstream via
ASGITransport, exactly like `test_chat_completions_route.py`, but with
a capturing transport wrapped around the mock so the test can inspect
the exact bytes that crossed the wire to "upstream" — the strongest
automated stand-in for a human running the manual curl gate.
"""

import json
from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from src.detect.tier1.checksum import verhoeff_generate_check_digit
from src.mock_upstream.main import app as mock_app
from src.proxy.upstream_client import get_upstream_client

_PAYLOAD = "23456789012"
_VALID_AADHAAR = _PAYLOAD + verhoeff_generate_check_digit(_PAYLOAD)
_VALID_PAN = "AAAPL1234C"


class _CapturingTransport(httpx.AsyncBaseTransport):
    """Wraps the mock upstream's own ASGITransport and records every
    request body that passes through it, so a test can assert on
    exactly what "left the gateway" — not just what the mock chose to
    echo back."""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        self._inner = inner
        self.captured_bodies: list[bytes] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.captured_bodies.append(request.content)
        return await self._inner.handle_async_request(request)


def _override_with_capturing_mock_upstream() -> _CapturingTransport:
    capturing = _CapturingTransport(httpx.ASGITransport(app=mock_app))

    def _get_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=capturing, base_url="http://mock-upstream")

    app.dependency_overrides[get_upstream_client] = _get_client
    return capturing


@pytest.fixture(autouse=True)
def _clear_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.pop(get_upstream_client, None)


def test_pan_and_aadhaar_in_a_tool_definition_never_reach_upstream_plaintext() -> None:
    capturing = _override_with_capturing_mock_upstream()
    client = TestClient(app, headers={"X-Session-Id": "test-session-1"})

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4",
            "messages": [{"role": "system", "content": "You are a helpful assistant."}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "lookup_customer",
                        "description": (
                            f"Look up a customer by Aadhaar {_VALID_AADHAAR} or PAN {_VALID_PAN}."
                        ),
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
            "stream": False,
        },
    )

    assert response.status_code == 200
    assert len(capturing.captured_bodies) == 1
    upstream_saw = json.loads(capturing.captured_bodies[0])
    upstream_saw_raw = json.dumps(upstream_saw)

    assert _VALID_AADHAAR not in upstream_saw_raw
    assert _VALID_PAN not in upstream_saw_raw

    description = upstream_saw["tools"][0]["function"]["description"]
    assert description.startswith("Look up a customer by Aadhaar ")
    assert " or PAN " in description
    assert description.endswith(".")


def test_the_same_identifier_gets_the_same_surrogate_in_every_json_location() -> None:
    """Same Aadhaar, three different structural locations (message
    content, tool description, tool-call arguments): the surrogate must
    be byte-identical everywhere. This is what "stateless, keyed FF1 —
    consistent by construction, no session coordination" (ARCHITECTURE.md,
    Surrogate Architecture) actually buys, proven end-to-end rather than
    only at the domain layer."""
    capturing = _override_with_capturing_mock_upstream()
    client = TestClient(app, headers={"X-Session-Id": "test-session-1"})

    arguments = json.dumps({"note": f"Aadhaar on file: {_VALID_AADHAAR}"})
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4",
            "messages": [
                {"role": "user", "content": f"My Aadhaar is {_VALID_AADHAAR}"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "log_note", "arguments": arguments},
                        }
                    ],
                },
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "log_note",
                        "description": f"Logs a note. Aadhaar on file: {_VALID_AADHAAR}",
                        "parameters": {
                            "type": "object",
                            "properties": {"note": {"type": "string"}},
                        },
                    },
                }
            ],
            "stream": False,
        },
    )

    assert response.status_code == 200
    upstream_saw = json.loads(capturing.captured_bodies[0])

    message_content = upstream_saw["messages"][0]["content"]
    tool_description = upstream_saw["tools"][0]["function"]["description"]
    tool_call_arguments = json.loads(
        upstream_saw["messages"][1]["tool_calls"][0]["function"]["arguments"]
    )["note"]

    message_surrogate = message_content.removeprefix("My Aadhaar is ")
    description_surrogate = tool_description.removeprefix("Logs a note. Aadhaar on file: ")
    arguments_surrogate = tool_call_arguments.removeprefix("Aadhaar on file: ")

    assert message_surrogate == description_surrogate == arguments_surrogate
    assert len(message_surrogate) == len(_VALID_AADHAAR)
    assert message_surrogate != _VALID_AADHAAR
    assert _VALID_AADHAAR not in json.dumps(upstream_saw)


def test_a_surrogate_replayed_in_a_later_request_on_the_same_session_is_not_re_encrypted() -> None:
    """The Phase 3 Task 3 scenario BUILD.md names directly: a surrogate
    minted on one turn, appearing again in a *later* request on the same
    session (e.g. the client replaying a prior assistant message), must
    pass through unchanged — never re-encrypted into a second, different
    surrogate ("a surrogate-of-a-surrogate unwinds one layer and
    corrupts silently")."""
    capturing = _override_with_capturing_mock_upstream()
    session_headers = {"X-Session-Id": "multi-turn-session"}
    client = TestClient(app, headers=session_headers)

    first = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4",
            "messages": [{"role": "user", "content": f"My Aadhaar is {_VALID_AADHAAR}"}],
            "stream": False,
        },
    )
    assert first.status_code == 200
    first_upstream_saw = json.loads(capturing.captured_bodies[0])
    surrogate = first_upstream_saw["messages"][0]["content"].removeprefix("My Aadhaar is ")
    assert surrogate != _VALID_AADHAAR

    second = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4",
            "messages": [
                {"role": "user", "content": f"My Aadhaar is {_VALID_AADHAAR}"},
                {"role": "assistant", "content": f"Noted: {surrogate}"},
                {"role": "user", "content": "thanks"},
            ],
            "stream": False,
        },
    )
    assert second.status_code == 200
    second_upstream_saw = json.loads(capturing.captured_bodies[1])

    # Turn 1's real value, replayed in turn 2's history, must still
    # encrypt to the exact same surrogate (consistent by construction).
    assert second_upstream_saw["messages"][0]["content"] == f"My Aadhaar is {surrogate}"
    # The surrogate itself, appearing in turn 2's history, must be left
    # exactly as-is — not detected as "a new real Aadhaar" and encrypted
    # a second time into something else.
    assert second_upstream_saw["messages"][1]["content"] == f"Noted: {surrogate}"
    assert _VALID_AADHAAR not in json.dumps(second_upstream_saw)
