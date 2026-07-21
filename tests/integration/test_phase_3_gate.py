"""Phase 3 closeout: the two BUILD.md proofs explicitly flagged, at
the time they were written, as belonging to "the final integration
task" rather than any single earlier one —

1. `test_session_names.py`'s and `test_session.py`'s own docstrings:
   "This is the Session-level half of BUILD.md's Phase 3 concurrency
   DoD item; the full-stack, HTTP-level version belongs to the final
   integration task."
2. BUILD.md's Phase 3 gate, verbatim: "A 5-turn conversation through
   the proxy, mock upstream forced to split every surrogate across 3
   chunks and to echo names in decorated/partial forms. Round-trip
   stays correct where matchable; misses are reported, not silently
   swallowed."

Tier 2 (PERSON/ORG/ADDRESS detection) doesn't exist until Phase 4, so
there is no detector yet to put a name surrogate into a session through
the real pipeline. The gate scenario below seeds a `PERSON` surrogate
directly via `Session.allocate_or_lookup_name()` — the same technique
`rehydration_fidelity`'s own harness and `tests/unit/test_rehydrate.py`
already use — into the *same* process-wide `SessionStore` singleton the
live route resolves via `Depends(get_session_store)`, then lets the
mock upstream's own verbatim-echo behaviour (it echoes whatever it
received) stand in for "the model returned the surrogate this way."
No production code changes; this is exactly the "no new production
functionality unless BUILD.md explicitly requires it" instruction.
"""

import json
import random
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from src.core.types import EntityType, SessionId
from src.detect.tier1.checksum import verhoeff_generate_check_digit
from src.mock_upstream.main import app as mock_app
from src.proxy.upstream_client import get_upstream_client
from src.session.names import DEFAULT_NAME_CANDIDATES
from src.session.store import get_session_store

_PERSON: EntityType = "PERSON"


def _override_with_capturing_mock_upstream() -> "_CapturingTransport":
    capturing = _CapturingTransport(httpx.ASGITransport(app=mock_app))

    def _get_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=capturing, base_url="http://mock-upstream")

    app.dependency_overrides[get_upstream_client] = _get_client
    return capturing


def _override_with_mock_upstream() -> None:
    def _get_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mock_app), base_url="http://mock-upstream"
        )

    app.dependency_overrides[get_upstream_client] = _get_client


@pytest.fixture(autouse=True)
def _clear_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.pop(get_upstream_client, None)


class _CapturingTransport(httpx.AsyncBaseTransport):
    """See `test_sanitize_integration.py` — same technique, duplicated
    locally rather than imported: it is test plumbing, not production
    logic, and each integration test module already keeps its own copy
    of this exact class."""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        self._inner = inner
        self.captured_bodies: list[bytes] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.captured_bodies.append(request.content)
        return await self._inner.handle_async_request(request)


def _parse_sse_content(raw: str) -> str:
    content = ""
    for line in raw.splitlines():
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        obj = json.loads(line[len("data: ") :])
        delta = obj["choices"][0]["delta"]
        content += delta.get("content", "")
    return content


def _valid_aadhaar(seed: int) -> str:
    payload = f"{seed:011d}"
    return payload + verhoeff_generate_check_digit(payload)


def test_fifty_concurrent_requests_on_one_session_lose_no_surrogate_mapping() -> None:
    """The full-stack counterpart to `test_session.py`'s and
    `test_session_names.py`'s own 50-thread, direct-`Session`-call
    concurrency tests: 50 real HTTP requests, same session, each
    introducing a distinct real Aadhaar. Every request's own round trip
    must stay correct (rehydrated response == the Aadhaar it sent), and
    every surrogate must have been durably recorded in the session's
    shared known-surrogate registry (Task 1) — the same registry every
    Tier-1 substitution writes into under `Session`'s own lock,
    regardless of whether the caller reached it via a direct method call
    or, as here, via 50 concurrent requests racing through the real
    route, sanitize(), and Session.record_surrogate()."""
    _override_with_mock_upstream()
    session_id = "phase-3-concurrency-gate"
    client = TestClient(app, headers={"X-Session-Id": session_id})
    aadhaars = [_valid_aadhaar(i) for i in range(50)]

    def _round_trip(aadhaar: str) -> str:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4",
                "messages": [{"role": "user", "content": f"My Aadhaar is {aadhaar}."}],
                "stream": False,
            },
        )
        assert response.status_code == 200
        content: str = response.json()["choices"][0]["message"]["content"]
        return content

    with ThreadPoolExecutor(max_workers=50) as pool:
        results = list(pool.map(_round_trip, aadhaars))

    for aadhaar, content in zip(aadhaars, results, strict=True):
        assert content == f"My Aadhaar is {aadhaar}."

    # Every one of the 50 concurrently-minted surrogates survived in the
    # session's shared known-surrogate registry — none lost to a race.
    session = get_session_store().get_or_create(SessionId(session_id))
    assert len(session.known_surrogate_snapshot()) >= 50


def test_five_turn_conversation_with_forced_chunking_and_decorated_partial_names() -> None:
    """The literal BUILD.md Phase 3 gate. Five turns, every streaming
    response forced across 3 chunks:

    1. Introduce a real Aadhaar.
    2. Replay turn 1's history (proving no double-encryption) *and*
       introduce a decorated name surrogate — must rehydrate.
    3. A partial (first-name-only) form of the same surrogate — must
       NOT rehydrate; the surrogate stays visible (a reported miss),
       never corrupted into the wrong thing.
    4. Replay the Aadhaar a second time, deep in the conversation —
       still the same surrogate, still no corruption.
    5. Both the Aadhaar and the exact name surrogate in the same
       message — both must round-trip simultaneously.

    Throughout, the real Aadhaar must never appear in what the mock
    upstream actually received (the capturing transport proves it).
    """
    capturing = _override_with_capturing_mock_upstream()
    session_id = "phase-3-five-turn-gate"
    client = TestClient(app, headers={"X-Session-Id": session_id})
    aadhaar = _valid_aadhaar(999)

    # Seed a PERSON surrogate the way a real Tier-2 detector (Phase 4)
    # will eventually produce one -- into the exact same process-wide
    # SessionStore singleton the live route already depends on.
    session = get_session_store().get_or_create(SessionId(session_id))
    surrogate_name = session.allocate_or_lookup_name(
        "Ramesh Kumar",
        _PERSON,
        list(DEFAULT_NAME_CANDIDATES),
        random.Random(1),
        datetime.now(timezone.utc),
    )
    first_token = surrogate_name.split(" ")[0]

    def _stream(messages: list[dict[str, str]]) -> str:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4",
                "messages": messages,
                "stream": True,
                "chunking": {"n": 3},
            },
        )
        assert response.status_code == 200
        return _parse_sse_content(response.text)

    # Turn 1 -- introduce the real Aadhaar.
    turn1_user = {"role": "user", "content": f"My Aadhaar is {aadhaar}."}
    turn1_reply = _stream([turn1_user])
    assert turn1_reply == f"My Aadhaar is {aadhaar}."

    # Turn 2 -- replay turn 1 verbatim (the real value, exactly as the
    # client actually saw it) plus the assistant's own rehydrated
    # reply, then introduce the name surrogate decorated in markdown.
    turn2_user = {"role": "user", "content": f"Please loop in **{surrogate_name}**."}
    turn2_messages = [
        turn1_user,
        {"role": "assistant", "content": turn1_reply},
        turn2_user,
    ]
    turn2_reply = _stream(turn2_messages)
    assert turn2_reply == "Please loop in **Ramesh Kumar**."

    # Turn 3 -- a partial (first-name-only) form of the same surrogate.
    # Conservative matching must leave it exactly as the mock echoed
    # it: a visible surrogate, not the real name, and not corrupted.
    turn3_user = {"role": "user", "content": f"{first_token} needs a callback."}
    turn3_messages = [*turn2_messages, {"role": "assistant", "content": turn2_reply}, turn3_user]
    turn3_reply = _stream(turn3_messages)
    assert turn3_reply == f"{first_token} needs a callback."
    assert "Ramesh Kumar" not in turn3_reply

    # Turn 4 -- replay the Aadhaar again, deep in a long conversation.
    turn4_user = {"role": "user", "content": f"Confirming, Aadhaar {aadhaar} again."}
    turn4_messages = [*turn3_messages, {"role": "assistant", "content": turn3_reply}, turn4_user]
    turn4_reply = _stream(turn4_messages)
    assert turn4_reply == f"Confirming, Aadhaar {aadhaar} again."

    # Turn 5 -- both entity kinds in one message; both must round-trip.
    turn5_user = {
        "role": "user",
        "content": f"{surrogate_name}, re: Aadhaar {aadhaar}, please close this out.",
    }
    turn5_messages = [*turn4_messages, {"role": "assistant", "content": turn4_reply}, turn5_user]
    turn5_reply = _stream(turn5_messages)
    assert turn5_reply == f"Ramesh Kumar, re: Aadhaar {aadhaar}, please close this out."

    # The real Aadhaar must never once have crossed the wire to
    # "upstream" in plaintext, across all five turns.
    for captured_body in capturing.captured_bodies:
        assert aadhaar.encode() not in captured_body
