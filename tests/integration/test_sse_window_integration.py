"""Proves the SSE layer composes cleanly with SlidingWindow: end-to-end
byte-identical reassembly through parse -> window -> serialize, with
the raw SSE bytes themselves fed in arbitrary network fragments.

Phase 1 has no substitution logic, so released text passes through
unchanged here — the same "prove the seam, not the matching" scope as
SlidingWindow's own Phase 1 tests.

Known Phase 1 simplification, stated rather than hidden: when the
window releases buffered text that spans more than one upstream SSE
event (e.g. the tail of event N held back until event N+1 arrives), or
when flush() releases a final remainder with no following content
event, this test wraps that text using the *most recently seen*
ContentDelta's envelope as a carrier. That is a reasonable answer for
Phase 1, where content is never modified and only byte-identical
reassembly is being proven. It is not a general answer to "which
detected span does this piece of text belong to," because nothing yet
tracks spans across event boundaries — that is Phase 3's problem, once
real matching exists, and deliberately not solved here.
"""

import json

import pytest

from src.core.chunking import split_into_n_chunks
from src.pipeline.sliding_window import SlidingWindow
from src.proxy.chat_stream import ContentDelta, DoneMarker, parse_event, serialize_content_delta
from src.proxy.sse_framing import SSEEventParser


def _build_raw_stream(content_pieces: list[str]) -> str:
    """Build a realistic multi-event SSE stream, the same shape the
    mock upstream (Task 3) emits."""
    lines = []
    for piece in content_pieces:
        obj = {
            "id": "chatcmpl-1",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "gpt-4",
            "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}],
        }
        lines.append(f"data: {json.dumps(obj)}\n\n")
    lines.append("data: [DONE]\n\n")
    return "".join(lines)


@pytest.mark.parametrize("fragment_n", [1, 2, 3, 7, 20, 50])
def test_content_survives_parse_window_serialize_under_arbitrary_fragmentation(
    fragment_n: int,
) -> None:
    original_pieces = ["ABC", "DE1", "234", "F was approved for Ramesh Kumar"]
    expected_content = "".join(original_pieces)
    raw_stream = _build_raw_stream(original_pieces)

    parser = SSEEventParser()
    window = SlidingWindow(lookahead=5)
    reassembled = ""
    last_content_delta: ContentDelta | None = None

    def emit(text: str) -> None:
        nonlocal reassembled
        if not text:
            return
        assert last_content_delta is not None, "content released before any event carried content"
        line = serialize_content_delta(last_content_delta, text)
        payload = json.loads(line[len("data: ") : -2])
        reassembled += payload["choices"][0]["delta"]["content"]

    for network_fragment in split_into_n_chunks(raw_stream, fragment_n):
        for sse_event in parser.feed(network_fragment):
            parsed = parse_event(sse_event)
            if isinstance(parsed, DoneMarker):
                emit(window.flush())
                continue
            last_content_delta = parsed
            emit(window.feed(parsed.content))

    for sse_event in parser.flush():
        parsed = parse_event(sse_event)
        if isinstance(parsed, DoneMarker):
            emit(window.flush())

    assert reassembled == expected_content


def test_zero_content_upstream_events_do_not_break_reassembly() -> None:
    """The mock's pathological chunking (Task 3) can emit far more
    events than there are characters, producing zero-content deltas.
    These must flow through the whole seam without corrupting output.
    """
    original_pieces = ["a", "", "", "b", "", "c"]
    expected_content = "abc"
    raw_stream = _build_raw_stream(original_pieces)

    parser = SSEEventParser()
    window = SlidingWindow(lookahead=2)
    reassembled = ""
    last_content_delta: ContentDelta | None = None

    for sse_event in parser.feed(raw_stream) + parser.flush():
        parsed = parse_event(sse_event)
        if isinstance(parsed, DoneMarker):
            released = window.flush()
        else:
            last_content_delta = parsed
            released = window.feed(parsed.content)
        if released:
            assert last_content_delta is not None
            line = serialize_content_delta(last_content_delta, released)
            payload = json.loads(line[len("data: ") : -2])
            reassembled += payload["choices"][0]["delta"]["content"]

    assert reassembled == expected_content
