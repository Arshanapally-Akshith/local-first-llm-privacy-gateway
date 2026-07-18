"""Tests for the generic SSE line/event parser — no OpenAI-specific
knowledge, just WHATWG SSE framing rules.
"""

import pytest

from src.core.chunking import split_into_n_chunks
from src.proxy.sse_framing import SSEEvent, SSEEventParser


def test_parses_single_complete_event_in_one_feed() -> None:
    parser = SSEEventParser()

    events = parser.feed('data: {"a": 1}\n\n')

    assert events == [SSEEvent(data='{"a": 1}')]


def test_parses_multiple_events_in_one_feed() -> None:
    parser = SSEEventParser()

    events = parser.feed("data: one\n\ndata: two\n\n")

    assert events == [SSEEvent(data="one"), SSEEvent(data="two")]


def test_partial_event_across_feed_calls_only_dispatches_once_complete() -> None:
    parser = SSEEventParser()

    assert parser.feed("data: hel") == []
    assert parser.feed("lo\n") == []  # data line complete, but no blank line yet
    assert parser.feed("\n") == [SSEEvent(data="hello")]


def test_crlf_pair_split_exactly_across_feed_calls_is_one_line_ending() -> None:
    parser = SSEEventParser()

    assert parser.feed("data: x\r") == []
    assert parser.feed("\n\r\n") == [SSEEvent(data="x")]


def test_bare_cr_line_endings() -> None:
    parser = SSEEventParser()

    events = parser.feed("data: x\r\r")  # bare CR terminator, twice: "data: x" then blank

    assert events == [SSEEvent(data="x")]


def test_bare_lf_line_endings() -> None:
    parser = SSEEventParser()

    events = parser.feed("data: x\n\n")

    assert events == [SSEEvent(data="x")]


def test_multiple_data_lines_join_with_newline_per_spec() -> None:
    parser = SSEEventParser()

    events = parser.feed("data: line1\ndata: line2\n\n")

    assert events == [SSEEvent(data="line1\nline2")]


def test_comment_lines_are_ignored() -> None:
    parser = SSEEventParser()

    events = parser.feed(": this is a comment\ndata: real\n\n")

    assert events == [SSEEvent(data="real")]


def test_unknown_fields_are_ignored() -> None:
    parser = SSEEventParser()

    events = parser.feed("event: message\nid: 5\ndata: real\n\n")

    assert events == [SSEEvent(data="real")]


def test_blank_lines_with_no_pending_data_produce_no_event() -> None:
    parser = SSEEventParser()

    assert parser.feed("\n\n\n") == []


def test_only_one_leading_space_after_colon_is_stripped() -> None:
    parser = SSEEventParser()

    events = parser.feed("data:  two spaces\n\n")

    assert events == [SSEEvent(data=" two spaces")]


def test_flush_dispatches_pending_event_with_no_trailing_blank_line() -> None:
    parser = SSEEventParser()
    parser.feed("data: incomplete")

    events = parser.flush()

    assert events == [SSEEvent(data="incomplete")]


def test_flush_with_nothing_pending_returns_empty() -> None:
    parser = SSEEventParser()

    assert parser.flush() == []


def test_empty_data_value_produces_an_event_with_empty_data() -> None:
    parser = SSEEventParser()

    events = parser.feed("data:\n\n")

    assert events == [SSEEvent(data="")]


@pytest.mark.parametrize("n", [1, 2, 3, 5, 10, 25])
def test_arbitrary_fragmentation_of_a_known_multi_event_stream(n: int) -> None:
    """The chunk-boundary torture test for the SSE layer, mirroring
    SlidingWindow's own — the same input, split N ways, must produce
    the same events regardless of where the fragmentation lands.
    """
    raw = 'data: {"a": 1}\n\ndata: {"b": 2}\n\ndata: [DONE]\n\n'
    parser = SSEEventParser()
    events: list[SSEEvent] = []

    for piece in split_into_n_chunks(raw, n):
        events.extend(parser.feed(piece))
    events.extend(parser.flush())

    assert events == [
        SSEEvent(data='{"a": 1}'),
        SSEEvent(data='{"b": 2}'),
        SSEEvent(data="[DONE]"),
    ]
