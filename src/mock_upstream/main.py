"""Mock upstream — OpenAI-compatible echo server.

The default upstream: test harness, CI backbone, and demo, in that
order of importance (ARCHITECTURE.md, Component 2, Mock Provider).
Echoes the last message's content back as the assistant's reply. Runs
as its own standalone process, reached by the proxy over real HTTP via
UPSTREAM_BASE_URL — mock and live upstreams are interchangeable purely
by which URL is configured (see docs/DECISIONS.md).

Not a stub: this is the only component that can produce the failure
conditions the gateway exists to survive (forced pathological chunk
boundaries), and the reason the whole demo runs with zero keys.
"""

import json
import time
import uuid
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from src.mock_upstream.chunking import resolve_chunks

app = FastAPI()

_DEFAULT_MODEL_NAME = "mock-gpt"


class ChatMessage(BaseModel):
    role: str
    content: str


class ChunkingDirective(BaseModel):
    """Optional, mock-only request field. A real OpenAI SDK call never
    sends this, so it defaults to absent and the mock falls back to the
    default word-ish split — see chunking.resolve_chunks."""

    n: int


class ChatCompletionRequest(BaseModel):
    # Tolerates the many real-SDK fields this mock doesn't model
    # (temperature, top_p, tools, ...) rather than rejecting them with
    # a 422 — an OpenAI-compatible surface must accept an OpenAI-shaped
    # body, not just the subset this mock happens to care about.
    model_config = ConfigDict(extra="ignore")

    model: str
    messages: list[ChatMessage]
    stream: bool = False
    chunking: ChunkingDirective | None = None


def _echoed_content(request: ChatCompletionRequest) -> str:
    """Echo the last message's content — this is what makes 'what the
    upstream actually received' visible end-to-end (ARCHITECTURE.md,
    Mock Provider)."""
    if not request.messages:
        return ""
    return request.messages[-1].content


def _completion_id() -> str:
    return f"chatcmpl-mock-{uuid.uuid4().hex[:24]}"


def _chunk_object(
    completion_id: str,
    created: int,
    model: str,
    *,
    delta: dict[str, str],
    finish_reason: str | None = None,
) -> dict[str, object]:
    return {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


def _sse_line(obj: dict[str, object]) -> str:
    return f"data: {json.dumps(obj)}\n\n"


async def _stream_response(request: ChatCompletionRequest, content: str) -> AsyncIterator[str]:
    completion_id = _completion_id()
    created = int(time.time())
    model = request.model or _DEFAULT_MODEL_NAME
    directive_n = request.chunking.n if request.chunking else None

    yield _sse_line(
        _chunk_object(completion_id, created, model, delta={"role": "assistant", "content": ""})
    )

    for piece in resolve_chunks(content, directive_n):
        yield _sse_line(_chunk_object(completion_id, created, model, delta={"content": piece}))

    yield _sse_line(_chunk_object(completion_id, created, model, delta={}, finish_reason="stop"))
    yield "data: [DONE]\n\n"


def _non_streaming_response(request: ChatCompletionRequest, content: str) -> dict[str, object]:
    word_count = len(content.split())
    return {
        "id": _completion_id(),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.model or _DEFAULT_MODEL_NAME,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": word_count,
            "completion_tokens": word_count,
            "total_tokens": 2 * word_count,
        },
    }


@app.post("/v1/chat/completions", response_model=None)
async def chat_completions(
    request: ChatCompletionRequest,
) -> StreamingResponse | dict[str, object]:
    content = _echoed_content(request)

    if not request.stream:
        return _non_streaming_response(request, content)
    return StreamingResponse(_stream_response(request, content), media_type="text/event-stream")
