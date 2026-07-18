"""Compatibility tests: the real, official openai Python SDK against the
real gateway, via httpx.ASGITransport — no running server, no monkey
patches, no custom adapters. These validate wire compatibility (does
the unmodified SDK work against this app), not the gateway's internals
— the gateway's own behavior is already covered by
test_chat_completions_route.py.

AsyncOpenAI + httpx.AsyncClient is required here, not the sync OpenAI
client: httpx.ASGITransport only drives async ASGI apps, so it only
works with an async httpx client. anyio's pytest plugin (already a
transitive dependency via httpx/starlette) provides @pytest.mark.anyio
async test support with no new dependency beyond openai itself.
"""

from collections.abc import Iterator

import httpx
import pytest
from openai import AsyncOpenAI

from app.main import app
from src.mock_upstream.main import app as mock_app
from src.proxy.upstream_client import get_upstream_client


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _use_mock_upstream() -> Iterator[None]:
    def _get_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mock_app), base_url="http://mock-upstream"
        )

    app.dependency_overrides[get_upstream_client] = _get_client
    yield
    app.dependency_overrides.pop(get_upstream_client, None)


def _sdk_client() -> AsyncOpenAI:
    """The official SDK, pointed at the gateway exactly as a real
    integration would — only the base_url changes, per the project's
    one-line pitch (ARCHITECTURE.md, One-line integration). The
    transport substitution is test plumbing (no real socket), not an
    adapter around the SDK's own request/response handling.
    """
    return AsyncOpenAI(
        base_url="http://gateway.test/v1",
        api_key="test-key-not-real",
        http_client=httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gateway.test"
        ),
    )


@pytest.mark.anyio
async def test_sdk_non_streaming_chat_completion() -> None:
    client = _sdk_client()

    response = await client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": "Hello world"}],
    )

    assert response.object == "chat.completion"
    assert response.choices[0].message.content == "Hello world"
    assert response.choices[0].finish_reason == "stop"


@pytest.mark.anyio
async def test_sdk_streaming_chat_completion_reassembles_content() -> None:
    client = _sdk_client()

    stream = await client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": "ABCDE1234F"}],
        stream=True,
    )

    content = ""
    saw_final_chunk = False
    async for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            content += delta.content
        if chunk.choices[0].finish_reason == "stop":
            saw_final_chunk = True

    assert content == "ABCDE1234F"
    assert saw_final_chunk


@pytest.mark.anyio
async def test_sdk_streaming_survives_pathological_upstream_chunking() -> None:
    """Not re-testing chunking correctness (Task 5 already does, at the
    HTTP level) — proving the *SDK's own* SSE parser, not just this
    project's, tolerates what the mock's forced pathological chunking
    produces, since that's the thing an adapter or monkey patch could
    otherwise have been hiding.
    """
    client = _sdk_client()

    stream = await client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": "ABCDE1234F was approved for review"}],
        stream=True,
        extra_body={"chunking": {"n": 25}},
    )

    content = "".join(
        [chunk.choices[0].delta.content async for chunk in stream if chunk.choices[0].delta.content]
    )

    assert content == "ABCDE1234F was approved for review"
