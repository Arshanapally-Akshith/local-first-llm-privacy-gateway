"""Mixed-radix positional encoding — pure math, independent of FF1.

FF1 permutes a sequence of digits that all share one radix. Some
entity domains (PAN, IFSC, vehicle registration) mix letters and
digits at different positions — different radixes per position — and
NIST's own guidance is that FF1 should not be applied to any single
segment smaller than the recommended 10^6 domain-size minimum
(ARCHITECTURE.md: "FF1 also has known small-domain caveats, which is
why it is applied to 10–16 digit domains and not to short fields").
Several of these entities' individual same-radix segments (e.g. PAN's
4 free digits, 10^4) fall below that minimum on their own.

This module's job is narrow: combine a mixed-radix symbol sequence
into a single integer (`encode`), and split an integer back into that
same shape (`decode`) — so a domain module can combine all its free
positions into one large-enough integer before handing a uniform-radix
digit list to FF1 (via the same `encode`/`decode` pair, since a
uniform radix is just the special case of every position sharing one
radix), then split the result back into its original per-position
alphabet afterward.

Deliberately has no dependency on `src/surrogate/ff1.py` and no
awareness that FF1 exists — its own correctness invariant,
`decode(encode(x, radixes), radixes) == x`, is verified entirely on
its own terms (`tests/unit/test_mixed_radix.py`), not via any
FF1-mediated round trip. Coupling the two would make a mixed-radix
bug and an FF1 bug indistinguishable from a single failing test.
"""

from collections.abc import Sequence


def encode(symbols: Sequence[int], radixes: Sequence[int]) -> int:
    """Combine `symbols` (most significant first, `symbols[i]` in
    `[0, radixes[i])`) into a single non-negative integer via
    place-value positional encoding — the same construction as
    ordinary base-`radix` numerals, generalized to a different radix
    per position.

    `radixes` with every entry equal is exactly ordinary uniform-radix
    base conversion; this is the mechanism domain modules use to turn
    a combined mixed-radix integer into the uniform digit list FF1
    requires — see this module's docstring.
    """
    value = 0
    for symbol, radix in zip(symbols, radixes, strict=True):
        value = value * radix + symbol
    return value


def decode(value: int, radixes: Sequence[int]) -> list[int]:
    """Invert `encode`: split `value` back into per-position symbols
    matching `radixes`, most significant first.

    Precondition: `0 <= value < domain_size(radixes)`. A caller
    passing a `value` outside this range gets a result whose symbols
    are still each individually within their radix (`%` guarantees
    that), but which will not round-trip back through `encode` to the
    same `value` — that's a caller error, not something this function
    detects, since it has no way to distinguish "value" from
    "value + k * domain_size(radixes)" without being told the bound.
    """
    symbols = [0] * len(radixes)
    for i in range(len(radixes) - 1, -1, -1):
        symbols[i] = value % radixes[i]
        value //= radixes[i]
    return symbols


def domain_size(radixes: Sequence[int]) -> int:
    """The total number of distinct symbol sequences `radixes`
    describes — `product(radixes)`. What a domain module compares
    against NIST's recommended FF1 minimum, and what it uses to choose
    a covering uniform radix/length for the FF1 call itself."""
    size = 1
    for radix in radixes:
        size *= radix
    return size
