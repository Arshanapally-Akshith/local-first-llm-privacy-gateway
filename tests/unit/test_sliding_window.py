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


def test_default_transform_is_identity_and_reproduces_phase_1_behaviour() -> None:
    """`transform=None` (the default) must be indistinguishable from
    Phase 1's original pure pass-through window — every test above
    exercises exactly that mode, unchanged."""
    window = SlidingWindow(lookahead=5)

    released = window.feed(_TORTURE_STRING)
    released += window.flush()

    assert released == _TORTURE_STRING


def _replacing_transform(buf: str) -> str:
    return buf.replace("XX", "REPLACED")


@pytest.mark.parametrize("n", [1, 2, 3, 5, 10, 25])
def test_transform_catches_a_match_split_across_n_chunks_before_any_of_it_is_released(
    n: int,
) -> None:
    """The literal BUILD.md Phase 3 scenario: a marker ("XX", standing
    in for a real surrogate) split across an arbitrary number of
    network fragments must still be found and substituted whole — never
    released partially, character by character, before the transform
    ever sees it complete (see sliding_window.py's module docstring for
    why this requires lookahead >= the longest match transform can ever
    find, and why applying transform after slicing cannot work)."""
    source = "before XX after"
    window = SlidingWindow(lookahead=2, transform=_replacing_transform)

    released = "".join(window.feed(piece) for piece in split_into_n_chunks(source, n))
    released += window.flush()

    assert released == "before REPLACED after"
    assert "XX" not in released


def test_transform_runs_on_flush_for_content_that_never_exceeded_lookahead() -> None:
    """Short content that never triggers an incremental release must
    still be transformed at flush() — the final chunk of a short
    response is exactly this case."""
    window = SlidingWindow(lookahead=100, transform=_replacing_transform)

    window.feed("XX")

    assert window.flush() == "REPLACED"


def test_transform_receiving_one_character_at_a_time_never_leaks_a_partial_match() -> None:
    """The maximally pathological case: feed exactly one character per
    call. If substitution ran on the released *fragment* instead of the
    retained buffer (the bug this design avoids), each single-character
    fragment would never contain the whole "XX" marker and it would
    leak to the caller one character at a time."""
    window = SlidingWindow(lookahead=2, transform=_replacing_transform)
    source = "aXXb"

    released = "".join(window.feed(ch) for ch in source)
    released += window.flush()

    assert released == "aREPLACEDb"
