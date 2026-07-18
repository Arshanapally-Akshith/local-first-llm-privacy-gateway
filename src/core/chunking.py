"""Pathological chunk-splitting.

One implementation, used both by the sliding window's torture tests
(Phase 1, Task 2) and by the mock upstream's forced pathological
chunking (Phase 1, Task 3) — CLAUDE.md: "The pathological chunker
exists for this; use it everywhere on the response path."

Lives in core rather than pipeline: the mock upstream is a standalone
application, not a layer inside the gateway's proxy -> pipeline stack,
so pipeline is not somewhere mock_upstream can reach without an
unrelated cross-dependency between two otherwise-independent
subsystems. core is the one module both can depend on.
"""


def split_into_n_chunks(text: str, n: int) -> list[str]:
    """Split `text` into exactly `n` ordered pieces that concatenate
    back to `text` exactly.

    Has no notion of words or tokens — a real provider's chunk
    boundaries are arbitrary with respect to content, so this function
    does not try to respect them either; that is what makes it useful
    for proving a consumer handles arbitrary splits.

    `n=1` returns `[text]` unchanged. If `n` exceeds `len(text)`, the
    trailing pieces are empty strings rather than an error — BUILD.md's
    Phase 1 explicitly requires exercising zero-content chunks, so this
    is the intended behaviour, not an edge case to avoid.

    Raises:
        ValueError: `n < 1` — a zero-or-negative chunk count has no
            meaningful split to produce.
    """
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    base, remainder = divmod(len(text), n)
    pieces: list[str] = []
    start = 0
    for i in range(n):
        size = base + (1 if i < remainder else 0)
        pieces.append(text[start : start + size])
        start += size
    return pieces
