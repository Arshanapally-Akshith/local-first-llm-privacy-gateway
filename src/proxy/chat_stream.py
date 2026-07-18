"""OpenAI chat-completion-chunk semantics on top of generic SSE framing.

This is the seam between the HTTP stream and the privacy pipeline
(BUILD.md, Phase 1): `parse_event()` extracts decoded `delta.content`
text for downstream processing (the sliding window, and eventually
detection/rehydration); `serialize_content_delta()` re-serializes a
(possibly different) content string back into a valid SSE line.
Deliberately knows nothing about entities, surrogates, or matching —
those are the pipeline's job, not this module's (CLAUDE.md: "Domain
modules never import the proxy layer" — the inverse holds too, this
layer must not reach upward into anything privacy-specific).
"""

import copy
import json
from dataclasses import dataclass

from src.core.exceptions import UpstreamError
from src.proxy.sse_framing import SSEEvent

DONE_SENTINEL = "[DONE]"


@dataclass
class ContentDelta:
    """One decoded chat-completion-chunk event, ready for the privacy
    pipeline.
    """

    content: str
    """Extracted `choices[0].delta.content`. Empty string if the delta
    carried no content field — the role-establishing and finish_reason
    chunks legitimately have none — never None, so downstream text
    processing (the sliding window) has one type to handle, not two."""

    envelope: dict[str, object]
    """The full decoded JSON object, unmodified. Re-serialization
    substitutes a content string back into this structure rather than
    rebuilding it from scratch, so id/object/created/model/index/
    finish_reason — and anything a future provider adds that this
    module does not specifically know about — survive the round trip
    unchanged."""


@dataclass(frozen=True)
class DoneMarker:
    """The `[DONE]` sentinel, as a distinguishable type — callers do
    not sniff string content to recognize stream termination."""


def parse_event(event: SSEEvent) -> ContentDelta | DoneMarker:
    """Decode one raw SSE event into a chat-completion-chunk delta or
    the `[DONE]` sentinel.

    Raises:
        UpstreamError: `event.data` is neither `"[DONE]"` nor valid
            JSON shaped like a chat-completion-chunk (i.e. it has a
            `choices` key). The upstream returned something this proxy
            cannot interpret as a valid response — that must fail
            loudly (status_code=502), not propagate as an empty or
            guessed value (CLAUDE.md, Error Handling: "an unexpected
            state in the pipeline raises; it does not shrug and
            continue").
    """
    if event.data == DONE_SENTINEL:
        return DoneMarker()
    try:
        envelope = json.loads(event.data)
    except json.JSONDecodeError as exc:
        raise UpstreamError(
            "upstream SSE event data is not valid JSON and is not [DONE]",
            status_code=502,
        ) from exc
    if not isinstance(envelope, dict) or "choices" not in envelope:
        raise UpstreamError(
            "upstream SSE event JSON is not shaped like a chat-completion-chunk "
            "(missing 'choices')",
            status_code=502,
        )
    return ContentDelta(content=_extract_content(envelope), envelope=envelope)


def _extract_content(envelope: dict[str, object]) -> str:
    """Best-effort extraction: a chunk legitimately missing a nested
    content field (finish_reason chunks, role-establishing chunks) is
    normal, not malformed — only the top-level shape check in
    parse_event() is allowed to raise.
    """
    choices = envelope.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return ""
    delta = first_choice.get("delta")
    if not isinstance(delta, dict):
        return ""
    content = delta.get("content")
    return content if isinstance(content, str) else ""


def serialize_content_delta(delta: ContentDelta, content: str) -> str:
    """Re-serialize `delta`'s envelope as an SSE `data:` line, with
    `content` substituted into `choices[0].delta.content`.

    `content` is a separate parameter from `delta.content` on purpose.
    Phase 1 always passes them equal — no substitution logic exists
    yet — but this is exactly the seam Phase 3's rehydration engine
    needs: it calls this with a *different* string once real matching
    exists, and this module does not change at all.

    The original envelope is never mutated (deep-copied first) — a
    caller may still be holding `delta` for other purposes.
    """
    envelope = copy.deepcopy(delta.envelope)
    choices = envelope.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        inner_delta = choices[0].get("delta")
        if isinstance(inner_delta, dict) and "content" in inner_delta:
            inner_delta["content"] = content
    return f"data: {json.dumps(envelope)}\n\n"


def serialize_done() -> str:
    return f"data: {DONE_SENTINEL}\n\n"
