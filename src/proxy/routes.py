"""The gateway's /v1/chat/completions route.

Wires together the components earlier tasks built: SSEEventParser and
chat_stream (Phase 1) parse and re-serialize upstream SSE; SlidingWindow
(Phase 1; Phase 3 Task 4 added its `transform` seam) buffers response
text; `pipeline.sanitize` (Phase 2 Task 6; Phase 3 Task 3 added
ingress-surrogate recognition; Phase 4 Task 3 added the injected
`Tier2Model`, so Tier-1 and Tier-2 spans are both detected) replaces
every newly-detected entity with its surrogate before the body ever
reaches the upstream client, and leaves an already-recognised surrogate
from an earlier turn untouched; `pipeline.rehydrate` (Phase 3 Task 4) is
the response-path counterpart — every surrogate the upstream echoes
back, streaming or not, is replaced with its real value before the
caller ever sees it.

`get_tier2_model()` is the same `@lru_cache`d singleton
`app/main.py`'s startup warmup already constructs and warms — this
route depends on it via FastAPI's `Depends`, not a fresh construction,
so no request pays the model's own multi-second load cost (Phase 4
Task 2).

Every request must carry `X-Session-Id` (Phase 3 architectural
decision: explicit required session header, fail closed if missing) —
there is no derived or implicit fallback identity, per this project's
"no silent security defaults" pattern elsewhere in Settings.

`X-Session-Id` is a routing key, not a credential: it scopes which
`Session` a request's detection/rehydration reads and writes, and
nothing here authenticates the caller presenting it. See
`docs/LIMITATIONS.md`, "Session identifiers are routing keys, not
authentication credentials," for why that is not being fixed in this
phase, and "Session continuity exists only within a single gateway
process" for the corresponding deployment-shape caveat.

Upstream failures (connection errors, timeouts, malformed responses)
raise UpstreamError with a fixed status-code mapping, per
ARCHITECTURE.md's Error Handling flowchart — they are transport-layer
failures, not privacy-policy decisions, so they are deliberately NOT
routed through fail_mode.resolve_failure(), which exists for detector
failures specifically (see docs/DECISIONS.md). `sanitize()` can raise
SurrogateDomainError (UPI/email, no registered domain yet); that is
also not FAIL_MODE-gated — ARCHITECTURE.md's Error Handling flowchart
treats a surrogate domain mismatch as its own fixed branch, always a
500, never a pass-through, regardless of FAIL_MODE.
"""

import json
import random
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from src.core.clock import Clock, get_clock
from src.core.exceptions import UpstreamError
from src.core.fail_mode import FailMode, get_fail_mode
from src.core.logging import get_gateway_logger, log_event
from src.core.types import CorrelationId, SessionId, new_correlation_id
from src.detect.tier2.gliner_model import get_tier2_model
from src.detect.tier2.model import Tier2Model
from src.pipeline.field_walker import JSONValue
from src.pipeline.rehydrate import REQUIRED_WINDOW_LOOKAHEAD, rehydrate, rehydrate_body
from src.pipeline.sanitize import sanitize
from src.pipeline.sliding_window import SlidingWindow
from src.session.rng import get_rng
from src.proxy.chat_stream import (
    ContentDelta,
    DoneMarker,
    parse_event,
    serialize_content_delta,
    serialize_done,
)
from src.proxy.sse_framing import SSEEventParser
from src.proxy.upstream_client import get_upstream_client
from src.session.session import Session
from src.session.store import SessionStore, get_session_store
from src.surrogate.key_provider import KeyProvider, get_key_provider

router = APIRouter()

_CHAT_COMPLETIONS_PATH = "/v1/chat/completions"
_SESSION_ID_HEADER = "X-Session-Id"
_CORRELATION_ID_HEADER = "X-Correlation-Id"
"""Diagnostic-only response header (Phase 7): exposes the per-request
`correlation_id` `chat_completions()` already generates internally for
log correlation. Added specifically so the latency harness
(`latency/runner/`), which drives the gateway as a real subprocess over
real sockets rather than in-process, can match a request it just sent
to that request's own structured log lines in the gateway's captured
log file — there is no other way for an out-of-process caller to learn
which correlation_id a given response corresponds to. Carries no
authentication or authorization meaning, same as `X-Session-Id`
(see this module's own docstring)."""

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


def _forwardable_headers(
    headers: httpx.Headers, *, also_drop: frozenset[str] = frozenset()
) -> dict[str, str]:
    """Strip hop-by-hop headers (RFC 7230 §6.1) before relaying a
    response; everything else — including provider-specific headers
    this module has no opinion about — passes through unchanged.

    `also_drop` exists for `_forward_non_streaming`'s benefit: once a
    response body has been re-serialized after rehydration, the
    upstream's own `Content-Length` no longer describes it — even a
    no-op rehydration re-serializes via `json.dumps`, which is not
    guaranteed to be byte-identical to whatever the upstream originally
    sent. Forwarding the stale header verbatim would hand the client a
    length that doesn't match the actual body, which a correct HTTP
    client either truncates against or hangs waiting to complete —
    silently corrupting a response that is otherwise perfectly correct.
    Dropping it lets Starlette compute a fresh, accurate one from the
    real body it is about to send.
    """
    drop = _HOP_BY_HOP_HEADERS | also_drop
    return {k: v for k, v in headers.items() if k.lower() not in drop}


def _translate_upstream_connection_failure(exc: httpx.TransportError) -> UpstreamError:
    """The one place a raw httpx transport-layer failure becomes the
    `UpstreamError` both `_forward_non_streaming` and `_start_streaming`
    raise for a failed connection attempt — previously two byte-for-byte
    identical `except` blocks (Phase 7 hardening finding; see
    `docs/DECISIONS.md`).

    `httpx.TransportError` is the base class covering every category
    below; `httpx.TimeoutException` is itself one of its subclasses, so
    checking it first (504) and falling back to 502 for everything else
    is a strict widening of the previous `TimeoutException`/`ConnectError`
    pair, not a behavioural change for either of those two. Every newly
    covered category maps to 502 ("could not connect to upstream") for
    the same reason: from the caller's perspective, none of them
    produced a valid, complete exchange with the upstream — only *where*
    in the exchange it broke differs, which isn't a distinction this
    proxy's caller can act on differently. Per category:

    - `ConnectError` (already handled before this change) / `ReadError` /
      `WriteError` / `CloseError` (`httpx.NetworkError` family): the TCP
      connection failed to establish, or failed partway through the
      request/response exchange or its teardown — the same practical
      outcome as a failed connect, just at a different phase.
    - `RemoteProtocolError`: the upstream sent a response that violates
      HTTP framing — squarely "Bad Gateway" territory, the upstream's
      own fault.
    - `LocalProtocolError`: this side violated HTTP framing while
      constructing the request. Rare (request bodies here are ordinary
      JSON with standard headers) and root-caused elsewhere if it ever
      fires, but the practical outcome for this proxy's caller is
      identical — no valid exchange occurred — so it shares the same
      status rather than crashing to a generic, undifferentiated 500.
    - `ProxyError`: a failure in an intermediate proxy `httpx` was
      configured to use while trying to reach the upstream. The
      upstream itself was never reached, matching `ConnectError`'s own
      semantics.
    - `UnsupportedProtocol`: the configured URL's scheme isn't one the
      transport supports. `Settings`'s own `upstream_base_url` validator
      (Phase 7 hardening) already restricts this to `http`/`https` at
      startup, so this should not occur in practice — covered here only
      so a transport-level edge case doesn't crash to a generic 500
      instead of the same 502 every other unreachable-upstream case gets.

    Deliberately not covered by this function (unrelated failure
    shapes, not narrowed for lack of trying): `httpx.DecodingError` and
    `httpx.TooManyRedirects` are `RequestError` siblings of
    `TransportError`, not subclasses of it, and both presuppose a
    response was actually received — a different failure class from
    "could not exchange a request with the upstream at all." Neither is
    reachable in this codebase today (no `Content-Encoding` handling
    that could fail to decode; `httpx.AsyncClient` does not follow
    redirects here), so extending coverage to them is not a demonstrated
    need.
    """
    if isinstance(exc, httpx.TimeoutException):
        return UpstreamError("upstream request timed out", status_code=504)
    return UpstreamError("could not connect to upstream", status_code=502)


def _epoch_ms(moment: datetime) -> float:
    """Epoch milliseconds for a `Clock.now()` result — the plain,
    directly-diffable form `log_event`'s `timestamp_ms` parameter exists
    for (see that parameter's own docstring). Kept as a private helper
    here rather than on `Clock` itself: nothing about "render as epoch
    milliseconds" is a clock concern — every other caller of `Clock.now()`
    in this codebase works with the `datetime` directly.
    """
    return moment.timestamp() * 1000


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
    key_provider: KeyProvider = Depends(get_key_provider),
    session_store: SessionStore = Depends(get_session_store),
    clock: Clock = Depends(get_clock),
    tier2_model: Tier2Model = Depends(get_tier2_model),
    fail_mode: FailMode = Depends(get_fail_mode),
    rng: random.Random = Depends(get_rng),
) -> Response:
    session_id_header = request.headers.get(_SESSION_ID_HEADER)
    if not session_id_header:
        # Phase 3 architectural decision: explicit required session
        # header, fail closed if missing — no derived/implicit session
        # identity. Checked before the body is even parsed, matching
        # ARCHITECTURE.md's "validation happens before anything else."
        raise HTTPException(status_code=400, detail=f"{_SESSION_ID_HEADER} header is required")
    session = session_store.get_or_create(SessionId(session_id_header))

    parsed_body = await request.json()
    if not isinstance(parsed_body, dict):
        # ARCHITECTURE.md, Error Handling: "Malformed request -> 400 + typed
        # error, no upstream call, no detection." A syntactically valid JSON
        # array/string/number parses fine here but isn't a chat-completion
        # body; sanitize() assumes a dict, and running detection/FF1 over a
        # bare string body would be exactly the "detector sees an
        # unvalidated request" case that section rules out.
        raise HTTPException(status_code=400, detail="request body must be a JSON object")
    body: dict[str, JSONValue] = parsed_body
    correlation_id = new_correlation_id()
    sanitized_body = sanitize(
        body,
        key_provider,
        session,
        clock,
        tier2_model,
        fail_mode,
        rng,
        correlation_id=correlation_id,
    )
    if not bool(sanitized_body.get("stream", False)):
        return await _forward_non_streaming(
            client, sanitized_body, session, key_provider, correlation_id
        )
    return await _start_streaming(
        client, sanitized_body, session, key_provider, correlation_id, clock
    )


async def _forward_non_streaming(
    client: httpx.AsyncClient,
    body: dict[str, JSONValue],
    session: Session,
    key_provider: KeyProvider,
    correlation_id: CorrelationId,
) -> Response:
    try:
        upstream_response = await client.post(_CHAT_COMPLETIONS_PATH, json=body)
    except httpx.TransportError as exc:
        raise _translate_upstream_connection_failure(exc) from exc
    return Response(
        content=_rehydrated_content(upstream_response, session, key_provider, correlation_id),
        status_code=upstream_response.status_code,
        headers={
            **_forwardable_headers(
                upstream_response.headers, also_drop=frozenset({"content-length"})
            ),
            _CORRELATION_ID_HEADER: correlation_id,
        },
    )


def _rehydrated_content(
    upstream_response: httpx.Response,
    session: Session,
    key_provider: KeyProvider,
    correlation_id: CorrelationId,
) -> bytes:
    """Best-effort rehydration of a non-streaming upstream response body.

    Only a 2xx body shaped like a chat-completion JSON object is ever
    rehydrated: an error body (4xx/5xx, per ARCHITECTURE.md's Error
    Handling — "propagate verbatim") is not a chat-completion shape and
    must reach the caller exactly as the upstream sent it, unmodified.
    A 2xx body that fails to parse as a JSON object is passed through
    unchanged rather than raised on — conservative matching's visible-
    miss trade (ARCHITECTURE.md, Response Lifecycle) applies here too:
    an un-rehydrated surrogate is a measured miss, not a crash.
    """
    if upstream_response.status_code // 100 != 2:
        return upstream_response.content
    try:
        parsed = json.loads(upstream_response.content)
    except json.JSONDecodeError:
        return upstream_response.content
    if not isinstance(parsed, dict):
        return upstream_response.content
    rehydrated = rehydrate_body(parsed, session, key_provider, correlation_id=correlation_id)
    return json.dumps(rehydrated, ensure_ascii=False).encode("utf-8")


async def _start_streaming(
    client: httpx.AsyncClient,
    body: dict[str, JSONValue],
    session: Session,
    key_provider: KeyProvider,
    correlation_id: CorrelationId,
    clock: Clock,
) -> StreamingResponse:
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
    except httpx.TransportError as exc:
        raise _translate_upstream_connection_failure(exc) from exc
    return StreamingResponse(
        _generate_sse(stream_ctx, upstream_response, session, key_provider, correlation_id, clock),
        media_type="text/event-stream",
        headers={
            **_forwardable_headers(upstream_response.headers),
            _CORRELATION_ID_HEADER: correlation_id,
        },
    )


async def _generate_sse(
    stream_ctx: AbstractAsyncContextManager[httpx.Response],
    upstream_response: httpx.Response,
    session: Session,
    key_provider: KeyProvider,
    correlation_id: CorrelationId,
    clock: Clock,
) -> AsyncIterator[str]:
    def _rehydrate_buffer(buffered_text: str) -> str:
        return rehydrate(buffered_text, session, key_provider, correlation_id=correlation_id)

    parser = SSEEventParser()
    window = SlidingWindow(lookahead=REQUIRED_WINDOW_LOOKAHEAD, transform=_rehydrate_buffer)
    last_content_delta: ContentDelta | None = None
    pending_structural_delta: ContentDelta | None = None
    logger = get_gateway_logger()
    upstream_first_chunk_logged = False
    window_first_release_logged = False

    def _log_window_first_release_once() -> None:
        # Phase 7 latency harness: the first time the window actually
        # releases bytes toward the client is the window-observed TTFT
        # instant. Logged at most once per response — every branch below
        # that can release non-empty text calls this, and only the
        # first call across all of them does anything.
        nonlocal window_first_release_logged
        if not window_first_release_logged:
            log_event(
                logger,
                "latency.window_first_release",
                correlation_id=correlation_id,
                timestamp_ms=_epoch_ms(clock.now()),
            )
            window_first_release_logged = True

    try:
        async for text_chunk in upstream_response.aiter_text():
            if not upstream_first_chunk_logged:
                # Phase 7 latency harness: raw upstream TTFB, independent
                # of whether this first chunk carries content — the
                # window/rehydration tax is measured against this point,
                # not against a content-bearing chunk specifically.
                log_event(
                    logger,
                    "latency.upstream_first_chunk",
                    correlation_id=correlation_id,
                    timestamp_ms=_epoch_ms(clock.now()),
                )
                upstream_first_chunk_logged = True
            for sse_event in parser.feed(text_chunk):
                parsed = parse_event(sse_event)
                if isinstance(parsed, DoneMarker):
                    released = window.flush()
                    if released and last_content_delta is not None:
                        _log_window_first_release_once()
                        yield serialize_content_delta(last_content_delta, released)
                    if pending_structural_delta is not None:
                        yield serialize_content_delta(
                            pending_structural_delta, pending_structural_delta.content
                        )
                    yield serialize_done()
                    return
                if _has_content_slot(parsed):
                    last_content_delta = parsed
                    released = window.feed(parsed.content)
                    if released:
                        _log_window_first_release_once()
                        yield serialize_content_delta(parsed, released)
                else:
                    # Structural event with no content slot (the
                    # finish_reason chunk) — nothing to buffer, but
                    # forwarding it immediately would let it reach the
                    # client before content still held back in the
                    # window, corrupting order (finish_reason must be
                    # the last signal, not an early one). Defer it until
                    # the window is flushed, at [DONE] or the
                    # mid-stream-drop fallback below — whichever comes
                    # first. Only the most recent such event survives if
                    # more than one arrives; no real provider sends more
                    # than one per response.
                    pending_structural_delta = parsed
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
                _log_window_first_release_once()
                yield serialize_content_delta(parsed, released)
        else:
            pending_structural_delta = parsed
    final = window.flush()
    if final and last_content_delta is not None:
        _log_window_first_release_once()
        yield serialize_content_delta(last_content_delta, final)
    if pending_structural_delta is not None:
        yield serialize_content_delta(pending_structural_delta, pending_structural_delta.content)
    yield serialize_done()
