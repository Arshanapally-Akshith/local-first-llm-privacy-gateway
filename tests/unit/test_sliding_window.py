"""Chunk-boundary torture tests for SlidingWindow.

BUILD.md, Phase 1: "A known string split across 1/2/3/N chunks must
arrive intact through the window." Phase 1 has no substitution logic,
so "intact" here means byte-identical reassembly — proving the
buffering mechanics before Phase 3 plugs real matching into them.
"""

import pytest

from src.core.chunking import split_into_n_chunks
from src.pipeline.sliding_window import SlidingWindow

_TORTURE_STRING = "The PAN ABCDE1234F was approved for Ramesh Kumar."


@pytest.mark.parametrize("n", [1, 2, 3, 5, 10, 25, 50])
def test_window_reassembles_string_split_across_n_chunks(n: int) -> None:
    window = SlidingWindow(lookahead=5)
    pieces = split_into_n_chunks(_TORTURE_STRING, n)

    released = "".join(window.feed(piece) for piece in pieces)
    released += window.flush()

    assert released == _TORTURE_STRING


def test_window_handles_zero_content_chunks() -> None:
    window = SlidingWindow(lookahead=5)
    pieces = split_into_n_chunks(_TORTURE_STRING, 200)  # far more chunks than characters
    assert "" in pieces  # sanity: this split actually exercises empty chunks

    released = "".join(window.feed(piece) for piece in pieces)
    released += window.flush()

    assert released == _TORTURE_STRING


def test_window_never_holds_back_more_than_lookahead_before_flush() -> None:
    window = SlidingWindow(lookahead=5)
    total_fed = 0
    total_released = 0

    for ch in _TORTURE_STRING:
        total_fed += 1
        total_released += len(window.feed(ch))
        assert total_fed - total_released == min(5, total_fed)


def test_window_releases_nothing_while_under_lookahead() -> None:
    window = SlidingWindow(lookahead=100)

    released = window.feed(_TORTURE_STRING)

    assert released == ""


def test_window_flush_releases_everything_still_buffered() -> None:
    window = SlidingWindow(lookahead=100)
    window.feed(_TORTURE_STRING)

    assert window.flush() == _TORTURE_STRING


def test_window_flush_on_empty_window_returns_empty_string() -> None:
    window = SlidingWindow(lookahead=5)

    assert window.flush() == ""


def test_feed_after_flush_raises() -> None:
    window = SlidingWindow(lookahead=5)
    window.flush()

    with pytest.raises(RuntimeError, match="window is closed"):
        window.feed("more")


def test_double_flush_raises() -> None:
    window = SlidingWindow(lookahead=5)
    window.flush()

    with pytest.raises(RuntimeError, match="flush\\(\\) called twice"):
        window.flush()


def test_negative_lookahead_rejected() -> None:
    with pytest.raises(ValueError, match="lookahead must be >= 0"):
        SlidingWindow(lookahead=-1)


def test_zero_lookahead_releases_immediately() -> None:
    """lookahead=0 is a valid, degenerate case: pure pass-through."""
    window = SlidingWindow(lookahead=0)

    assert window.feed("abc") == "abc"
    assert window.flush() == ""
