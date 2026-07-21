"""Buffered sliding window — the response-path scaffold, now with the
Phase 3 substitution seam wired in.

Invariant: `feed()` never releases the trailing `lookahead` characters
of everything appended so far, because those characters might still be
the start of a surrogate that hasn't fully arrived (ARCHITECTURE.md,
Streaming Architecture: "never emit a byte that could still be part of
an unmatched surrogate"). `flush()` releases unconditionally — it is
the caller's signal that no more input is coming.

An optional `transform` callable — the actual rehydration engine, once
one exists (Phase 3 Task 4, `src/pipeline/rehydrate.py`) — is applied to
the *entire retained buffer* every time it changes, strictly before the
lookahead length check that decides how much is safe to release. This
ordering is load-bearing, not stylistic: a surrogate is only guaranteed
to be fully, contiguously present in `self._buffer` for the single
instant between "the last of its characters just arrived" and "its
first character is about to age out of the retention window" — and
that instant only exists at all if `lookahead >= transform`'s longest
possible match length. Applying `transform` *after* slicing (e.g. to
just the fragment `feed()` is about to return) is provably too late:
that fragment can be as short as one character, fed incrementally, and
by the time its first character is released, the rest of a longer
match may still be sitting in `self._buffer`, never released with it in
the same call — which is exactly how a naive per-chunk substitution
leaks a surrogate one character at a time (ARCHITECTURE.md, "Naive:
substitute per chunk... Result: surrogate leaks to user"). Applying it
to the whole buffer, every call, before slicing, is what makes "the
seam exists" (Phase 1's own description of this class) literally true:
this file still knows nothing about surrogates, entities, or sessions —
`transform` is injected, exactly like CLAUDE.md's dependency-injection
rule requires for a model, a key, or a clock.

`transform=None` (the default) reproduces Phase 1's original pure
pass-through behaviour exactly — every Phase 1 test in
`tests/unit/test_sliding_window.py` still exercises that mode
unchanged.
"""

from collections.abc import Callable

DEFAULT_LOOKAHEAD = 64
"""Fallback lookahead for a `SlidingWindow` constructed with no
`transform` (or by a test exercising the buffering mechanics in
isolation). The real response path (`src/proxy/routes.py`) never relies
on this default — it always passes an explicit, measured value from
`src/pipeline/rehydrate.py::REQUIRED_WINDOW_LOOKAHEAD`, derived from the
actual registered surrogate domains and name list, not a guess. This
constant predates that derivation (Phase 1, before Tier 1 or the name
list existed) and is kept only as a generic, privacy-unaware default
for this otherwise-generic class."""


class SlidingWindow:
    """Buffers text so a caller can safely pattern-match against a
    complete prefix before it is released, optionally substituting
    matches found in that prefix before it is ever handed back.
    """

    def __init__(
        self,
        lookahead: int = DEFAULT_LOOKAHEAD,
        transform: Callable[[str], str] | None = None,
    ) -> None:
        if lookahead < 0:
            raise ValueError(f"lookahead must be >= 0, got {lookahead}")
        self._lookahead = lookahead
        self._transform = transform
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
        # Transform the whole retained buffer, BEFORE deciding what is
        # safe to release below — never move this after the slice, and
        # never apply it to just `released`. Doing either "simplifies"
        # this back into a naive per-chunk substitution that provably
        # leaks a match one character at a time when chunks arrive
        # small (see the module docstring for the full argument, and
        # `test_transform_receiving_one_character_at_a_time_never_leaks_a_partial_match`
        # in tests/unit/test_sliding_window.py for the regression this
        # ordering exists to prevent).
        if self._transform is not None:
            self._buffer = self._transform(self._buffer)
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
        # Same ordering requirement as feed() above: transform the full
        # remaining buffer before it is handed back, not after.
        if self._transform is not None:
            self._buffer = self._transform(self._buffer)
        remaining, self._buffer = self._buffer, ""
        return remaining
