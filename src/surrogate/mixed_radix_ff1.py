"""Combine `mixed_radix.py` and `ff1.py` for domains whose free
positions don't share one radix (PAN, IFSC, vehicle registration).

Neither `mixed_radix.py` nor `ff1.py` knows the other exists — this
module is where they're wired together, deliberately kept out of
both, so a bug here can never be mistaken for a bug in either
independently-verified primitive.

## Why cycle-walking, and why it is correctly invertible here

A mixed-radix domain's true size (e.g. PAN's free positions: `26^5 *
10^4`) is essentially never an exact power of any convenient uniform
radix. FF1 needs a uniform radix. The standard reconciliation is
**cycle-walking**: pick a uniform "covering" domain (here, binary —
`2**bits` for the smallest `bits` with `2**bits >= true_size`) that's
at least as large as the true domain, permute within it, and if the
result lands outside the true domain's range, permute *its own
output* again with the *same* key and tweak, repeating until the
result lands inside — never changing the tweak between attempts.

That last part is what makes this correctly invertible. For a
permutation `F` on the covering domain, restricting to "walk forward
until landing in `V`" defines a genuine permutation of `V` *and its
own inverse is "walk backward until landing in `V`"* — provided the
real input is always itself a member of `V`. It is, here: any real
value passed to `encrypt` is a value this domain already accepts, so
its own mixed-radix encoding is always `< true_size` by construction.
(This does *not* generalize to every possible constrained-range
problem — see `docs/DECISIONS.md` for why Aadhaar's UIDAI
reserved-range requirement is a different, harder case, deliberately
not solved by this module.)
"""

from collections.abc import Callable, Sequence
from typing import Final

from src.core.exceptions import SurrogateDomainError
from src.surrogate import ff1, mixed_radix

_MAX_CYCLE_WALK_ATTEMPTS: Final[int] = 1000
"""A tightly-chosen covering domain (see `_covering_bits`) keeps the
expected number of attempts close to 1; this bound only exists to
turn a mistake elsewhere (e.g. a domain whose true_size is much
smaller than its covering domain) into a loud failure instead of an
infinite loop."""


def encrypt_combined(
    key: bytes, tweak: bytes, symbols: Sequence[int], radixes: Sequence[int]
) -> list[int]:
    """FF1-permute a mixed-radix symbol sequence via cycle-walking.

    `symbols`/`radixes` describe the domain's free positions only —
    frozen positions are the calling domain's concern, not this
    function's.
    """
    true_size = mixed_radix.domain_size(radixes)
    bits = _covering_bits(true_size)
    value = mixed_radix.encode(symbols, radixes)
    result = _walk(key, tweak, value, bits, true_size, ff1.ff1_encrypt)
    return mixed_radix.decode(result, radixes)


def decrypt_combined(
    key: bytes, tweak: bytes, symbols: Sequence[int], radixes: Sequence[int]
) -> list[int]:
    """Invert `encrypt_combined`."""
    true_size = mixed_radix.domain_size(radixes)
    bits = _covering_bits(true_size)
    value = mixed_radix.encode(symbols, radixes)
    result = _walk(key, tweak, value, bits, true_size, ff1.ff1_decrypt)
    return mixed_radix.decode(result, radixes)


def _covering_bits(true_size: int) -> int:
    """The smallest binary width whose domain (`2**bits`) is at least
    `true_size` — the tightest binary covering, minimizing the
    expected number of cycle-walk attempts."""
    return max((true_size - 1).bit_length(), 1)


def _walk(
    key: bytes,
    tweak: bytes,
    start: int,
    bits: int,
    true_size: int,
    permute: Callable[[bytes, bytes, int, list[int]], list[int]],
) -> int:
    current = start
    for _ in range(_MAX_CYCLE_WALK_ATTEMPTS):
        digits = mixed_radix.decode(current, [2] * bits)
        permuted_digits = permute(key, tweak, 2, digits)
        current = mixed_radix.encode(permuted_digits, [2] * bits)
        if current < true_size:
            return current
    raise SurrogateDomainError(
        f"mixed-radix cycle-walk did not converge within {_MAX_CYCLE_WALK_ATTEMPTS} attempts "
        f"(true_size={true_size}, covering_bits={bits}) — the covering domain may be far larger "
        "than the true domain for this input shape"
    )
