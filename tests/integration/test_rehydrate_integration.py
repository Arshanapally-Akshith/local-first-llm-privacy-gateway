"""End-to-end proof of Phase 3 Task 4's response-path wiring: a real
entity sanitized on the way out to the mock upstream, and echoed back
by it (as a surrogate — the mock only ever sees what the gateway sent),
must arrive back at the *caller* as the real value again — for both the
streaming and non-streaming response paths, including when the mock is
forced to split the surrogate across many SSE chunks (BUILD.md, Phase
3: "Split-surrogate rehydration passes across 1/2/3/N chunk splits").

Routes through the real `app`, the real `sanitize()`/`rehydrate()`
pipeline, and the real mock upstream via `ASGITransport` — the same
harness `test_sanitize_integration.py` and
`test_chat_completions_route.py` already use.
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


def _parse_sse_content(raw: str) -> str:
    content = ""
    for line in raw.splitlines():
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        obj = json.loads(line[len("data: ") :])
        delta = obj["choices"][0]["delta"]
        content += delta.get("content", "")
    return content


def test_non_streaming_response_is_rehydrated_to_the_real_value() -> None:
    _override_with_mock_upstream()
    client = TestClient(app, headers={"X-Session-Id": "rehydrate-non-streaming"})

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4",
            "messages": [{"role": "user", "content": f"My Aadhaar is {_VALID_AADHAAR}"}],
            "stream": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == f"My Aadhaar is {_VALID_AADHAAR}"


def test_streaming_response_is_rehydrated_to_the_real_value() -> None:
    _override_with_mock_upstream()
    client = TestClient(app, headers={"X-Session-Id": "rehydrate-streaming"})

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4",
            "messages": [{"role": "user", "content": f"My Aadhaar is {_VALID_AADHAAR}"}],
            "stream": True,
        },
    )

    assert response.status_code == 200
    assert _parse_sse_content(response.text) == f"My Aadhaar is {_VALID_AADHAAR}"


@pytest.mark.parametrize("n", [1, 2, 3, 12])
def test_streaming_response_rehydrates_a_surrogate_forced_across_n_chunks(n: int) -> None:
    """The literal Phase 3 gate scenario: the mock is forced to split
    the (sanitized) surrogate across `n` SSE chunks; the gateway must
    still reassemble and rehydrate it correctly regardless of where the
    chunk boundaries happen to fall relative to the surrogate."""
    _override_with_mock_upstream()
    client = TestClient(app, headers={"X-Session-Id": f"rehydrate-chunked-{n}"})

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4",
            "messages": [{"role": "user", "content": f"My Aadhaar is {_VALID_AADHAAR}"}],
            "stream": True,
            "chunking": {"n": n},
        },
    )

    assert response.status_code == 200
    assert _parse_sse_content(response.text) == f"My Aadhaar is {_VALID_AADHAAR}"


def test_non_streaming_response_content_length_matches_the_rehydrated_body() -> None:
    """Regression: the upstream's own Content-Length describes the
    *sanitized* body it sent, not the rehydrated one the gateway
    returns — forwarding it verbatim would hand the client a length
    that doesn't match the actual bytes sent."""
    _override_with_mock_upstream()
    client = TestClient(app, headers={"X-Session-Id": "rehydrate-content-length"})

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4",
            "messages": [{"role": "user", "content": f"My Aadhaar is {_VALID_AADHAAR}"}],
            "stream": False,
        },
    )

    assert response.status_code == 200
    assert int(response.headers["content-length"]) == len(response.content)
