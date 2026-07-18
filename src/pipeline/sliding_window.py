"""Buffered sliding window — the response-path scaffold.

Invariant: `feed()` never releases the trailing `lookahead` characters
of everything appended so far, because those characters might still be
the start of something that needs matching once real substitution logic
exists (Phase 3). `flush()` releases unconditionally — it is the
caller's signal that no more input is coming (ARCHITECTURE.md,
Streaming Architecture: "never emit a byte that could still be part of
an unmatched surrogate").

Phase 1 has no substitution logic yet, so nothing is actually matched
here. What this class proves now is that the buffering mechanics
themselves are correct — nothing dropped, nothing duplicated, correct
behaviour on empty chunks, correct final flush — so Phase 3 can plug
real matching into an already-proven scaffold (BUILD.md Phase 1: "the
seam exists and is tested").
"""

DEFAULT_LOOKAHEAD = 64
"""Guess. ARCHITECTURE.md says this should derive from the longest
entity in the surrogate domain plus the longest decoration handled —
neither exists yet (Tier 1 is Phase 2, name decoration handling is
Phase 3). Revisit once those are real; this value is not measured."""


class SlidingWindow:
    """Buffers text so a caller can safely pattern-match against a
    complete prefix before it is released.
    """

    def __init__(self, lookahead: int = DEFAULT_LOOKAHEAD) -> None:
        if lookahead < 0:
            raise ValueError(f"lookahead must be >= 0, got {lookahead}")
        self._lookahead = lookahead
        self._buffer = ""
        self._flushed = False

    def feed(self, chunk: str) -> str:
        """Append `chunk`; return the prefix now safe to release.

        Returns an empty string if the buffered content still fits
        within the lookahead margin — there is nothing safe to release
        yet, not an error.

        Raises:
            RuntimeError: called after `flush()` — the window is closed
                and continuing to feed it is a caller bug, not a state
                to accommodate silently.
        """
        if self._flushed:
            raise RuntimeError("feed() called after flush(); window is closed")
        self._buffer += chunk
        if len(self._buffer) <= self._lookahead:
            return ""
        release_upto = len(self._buffer) - self._lookahead
        released, self._buffer = self._buffer[:release_upto], self._buffer[release_upto:]
        return released

    def flush(self) -> str:
        """Release everything remaining. Call once, at stream end.

        Raises:
            RuntimeError: called a second time. A caller flushing twice
                almost certainly has a bug in its stream-end detection,
                and BUILD.md's named failure mode here — "truncated
                final output, the last sentence of every response" —
                is exactly the kind of defect that must be loud, not
                swallowed into a silent no-op.
        """
        if self._flushed:
            raise RuntimeError("flush() called twice on the same window")
        self._flushed = True
        remaining, self._buffer = self._buffer, ""
        return remaining
