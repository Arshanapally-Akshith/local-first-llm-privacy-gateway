"""The gateway's /v1/chat/completions route.

Wires together the components earlier tasks built: SSEEventParser and
chat_stream (Task 4) parse and re-serialize upstream SSE; SlidingWindow
(Task 2) buffers response text. No detection, matching, or substitution
— that is Phase 2+. This task only wires the transport pipeline
together (BUILD.md, Phase 1: "Bytes in, bytes out, correctly").

Upstream failures (connection errors, timeouts, malformed responses)
raise UpstreamError with a fixed status-code mapping, per
ARCHITECTURE.md's Error Handling flowchart — they are transport-layer
failures, not privacy-policy decisions, so they are deliberately NOT
routed through fail_mode.resolve_failure(), which exists for detector
failures specifically (see docs/DECISIONS.md).
"""

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager

import httpx
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse

from src.core.exceptions import UpstreamError
from src.pipeline.sliding_window import SlidingWindow
from src.proxy.chat_stream import (
    ContentDelta,
    DoneMarker,
    parse_event,
    serialize_content_delta,
    serialize_done,
)
from src.proxy.sse_framing import SSEEventParser
from src.proxy.upstream_client import get_upstream_client

router = APIRouter()

_CHAT_COMPLETIONS_PATH = "/v1/chat/completions"

_HOP_BY_HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
    }
)


def _forwardable_headers(headers: httpx.Headers) -> dict[str, str]:
    """Strip hop-by-hop headers (RFC 7230 §6.1) before relaying a
    response; everything else — including provider-specific headers
    this module has no opinion about — passes through unchanged."""
    return {k: v for k, v in headers.items() if k.lower() not in _HOP_BY_HOP_HEADERS}


def _has_content_slot(delta: ContentDelta) -> bool:
    """Whether `delta`'s envelope has a `choices[0].delta.content` key
    at all — the role-establishing and plain content chunks do; the
    finish_reason chunk (`delta: {}`) does not.

    Load-bearing distinction: `serialize_content_delta` deliberately
    never invents a `content` key on an envelope that never had one
    (Task 4, `test_serialize_content_delta_does_not_invent_a_content_key`
    — inventing one would make a finish_reason chunk look like it
    carries text a real provider never put there). That means whichever
    envelope is chosen as the carrier for text the window releases
    *must* already have a content slot, or the released text is
    silently dropped — exactly the bug this check exists to prevent.
    """
    choices = delta.envelope.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return False
    inner_delta = choices[0].get("delta")
    return isinstance(inner_delta, dict) and "content" in inner_delta


@router.post(_CHAT_COMPLETIONS_PATH)
async def chat_completions(
    request: Request,
    client: httpx.AsyncClient = Depends(get_upstream_client),
) -> Response:
    body = await request.json()
    if not bool(body.get("stream", False)):
        return await _forward_non_streaming(client, body)
    return await _start_streaming(client, body)


async def _forward_non_streaming(client: httpx.AsyncClient, body: dict[str, object]) -> Response:
    try:
        upstream_response = await client.post(_CHAT_COMPLETIONS_PATH, json=body)
    except httpx.TimeoutException as exc:
        raise UpstreamError("upstream request timed out", status_code=504) from exc
    except httpx.ConnectError as exc:
        raise UpstreamError("could not connect to upstream", status_code=502) from exc
    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=_forwardable_headers(upstream_response.headers),
    )


async def _start_streaming(client: httpx.AsyncClient, body: dict[str, object]) -> StreamingResponse:
    """Open the upstream connection before returning a StreamingResponse.

    Connection failures and timeouts happen here, outside the response
    generator, specifically so they can still become a real 502/504 HTTP
    status. Once StreamingResponse begins sending bytes to the client,
    the status code (200) is already committed and can never change —
    a failure after that point must be handled *inside* the stream
    (flush-and-terminate honestly), not raised as an exception FastAPI
    would try, too late, to turn into a different status code.
    """
    stream_ctx = client.stream("POST", _CHAT_COMPLETIONS_PATH, json=body)
    try:
        upstream_response = await stream_ctx.__aenter__()
    except httpx.TimeoutException as exc:
        raise UpstreamError("upstream request timed out", status_code=504) from exc
    except httpx.ConnectError as exc:
        raise UpstreamError("could not connect to upstream", status_code=502) from exc
    return StreamingResponse(
        _generate_sse(stream_ctx, upstream_response),
        media_type="text/event-stream",
        headers=_forwardable_headers(upstream_response.headers),
    )


async def _generate_sse(
    stream_ctx: AbstractAsyncContextManager[httpx.Response],
    upstream_response: httpx.Response,
) -> AsyncIterator[str]:
    parser = SSEEventParser()
    window = SlidingWindow()
    last_content_delta: ContentDelta | None = None

    try:
        async for text_chunk in upstream_response.aiter_text():
            for sse_event in parser.feed(text_chunk):
                parsed = parse_event(sse_event)
                if isinstance(parsed, DoneMarker):
                    released = window.flush()
                    if released and last_content_delta is not None:
                        yield serialize_content_delta(last_content_delta, released)
                    yield serialize_done()
                    return
                if _has_content_slot(parsed):
                    last_content_delta = parsed
                released = window.feed(parsed.content)
                if released:
                    yield serialize_content_delta(parsed, released)
    except (httpx.TransportError, UpstreamError):
        # Mid-stream drop, or a malformed event discovered mid-stream
        # (parse_event() raises UpstreamError for that — Task 4): by
        # this point StreamingResponse has already committed the 200
        # status, so neither can become a 502/504 anymore. Both fall
        # through to the same flush-and-terminate-honestly path a
        # clean-but-DONE-less close takes (ARCHITECTURE.md, Error
        # Handling: "Upstream mid-stream drop -> Flush window,
        # rehydrate what we have, terminate stream honestly"). A
        # malformed event on the very first chunk is included here too
        # — StreamingResponse sends response headers before this
        # generator is ever iterated, so "first chunk" is no earlier
        # from the client's perspective than any other.
        pass
    finally:
        await stream_ctx.__aexit__(None, None, None)

    for sse_event in parser.flush():
        try:
            parsed = parse_event(sse_event)
        except UpstreamError:
            # A trailing event truncated by the same drop that got us
            # here (e.g. a connection loss mid-JSON): already in
            # honest-termination mode, so drop it rather than crash the
            # generator over a malformed fragment we can't recover.
            continue
        if isinstance(parsed, DoneMarker):
            continue
        if _has_content_slot(parsed):
            last_content_delta = parsed
        released = window.feed(parsed.content)
        if released:
            yield serialize_content_delta(parsed, released)
    final = window.flush()
    if final and last_content_delta is not None:
        yield serialize_content_delta(last_content_delta, final)
    yield serialize_done()
