"""FF1 (NIST SP 800-38G) — generic format-preserving permutation.

A literal implementation of the FF1 algorithm exactly as specified in
NIST SP 800-38G: the Feistel-round structure, the P/Q byte layout, and
the PRF/S construction, using `cryptography`'s AES only as the
underlying block cipher. Deliberately not optimized or generalized
beyond what the spec itself parameterizes (key, tweak, radix, digit
list) — this module has zero knowledge of Aadhaar, PAN, IFSC, or any
other entity type. Domain-specific structure (alphabets, frozen
positions, mixed-radix combination, checksum repair) lives in
`src/surrogate/domain.py` and the concrete domain modules instead.

Every formula here (`b`, `d`, the `P`/`Q` byte layouts, the Feistel
update, the `S` construction) was hand-verified against NIST's own
published round-by-round trace before being trusted — not implemented
from memory alone. See `tests/unit/test_ff1.py`, which checks this
implementation against all nine of NIST's official FF1 sample vectors
(AES-128/192/256, radix 10 and 36, empty and non-empty tweak):
https://csrc.nist.gov/csrc/media/projects/cryptographic-standards-and-guidelines/documents/examples/ff1samples.pdf
"""

import math
from typing import Final

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from src.core.exceptions import SurrogateDomainError

_ROUNDS: Final[int] = 10
"""NIST SP 800-38G fixes FF1's Feistel round count at 10 — not a
tunable parameter, and not related to `radix` or digit-list length."""

_MIN_RADIX: Final[int] = 2
_MAX_RADIX: Final[int] = 2**16
"""SP 800-38G's stated radix bound for FF1."""

_MIN_LENGTH: Final[int] = 2
"""FF1 splits its input into two non-empty Feistel halves; a
single-digit input has no valid split."""

_MAX_TWEAK_LENGTH: Final[int] = 2**32 - 1


def ff1_encrypt(key: bytes, tweak: bytes, radix: int, digits: list[int]) -> list[int]:
    """Permute `digits` (each in `[0, radix)`) under `key`/`tweak`, per
    NIST SP 800-38G's FF1.Encrypt. Pure permutation only.

    Raises:
        SurrogateDomainError: `radix` or `len(digits)` is outside
            FF1's supported range.
    """
    _validate(radix, len(digits), tweak)
    u, v, b, d = _feistel_params(radix, len(digits), tweak)
    p = _build_p(radix, u, len(digits), len(tweak))

    a = digits[:u]
    b_half = digits[u:]
    for i in range(_ROUNDS):
        q = _build_q(tweak, b, i, b_half, radix)
        r = _prf(key, p + q)
        s = _generate_s(key, r, d)
        m = u if i % 2 == 0 else v
        y = int.from_bytes(s, "big")
        c = (_num_radix(a, radix) + y) % (radix**m)
        c_digits = _str_m_radix(c, radix, m)
        a, b_half = b_half, c_digits
    return a + b_half


def ff1_decrypt(key: bytes, tweak: bytes, radix: int, digits: list[int]) -> list[int]:
    """Invert `ff1_encrypt`:
    `ff1_decrypt(key, tweak, radix, ff1_encrypt(key, tweak, radix, digits)) == digits`
    for every valid `digits`.

    The Feistel update mirrors `ff1_encrypt`'s exactly, run in reverse
    round order, with the roles of `a`/`b_half` in the `Q` construction
    and the add/subtract step swapped accordingly — verified against
    NIST's own decrypt trace, not derived by assumption from the
    encrypt formula alone.

    Raises:
        SurrogateDomainError: `radix` or `len(digits)` is outside
            FF1's supported range.
    """
    _validate(radix, len(digits), tweak)
    u, v, b, d = _feistel_params(radix, len(digits), tweak)
    p = _build_p(radix, u, len(digits), len(tweak))

    a = digits[:u]
    b_half = digits[u:]
    for i in range(_ROUNDS - 1, -1, -1):
        q = _build_q(tweak, b, i, a, radix)
        r = _prf(key, p + q)
        s = _generate_s(key, r, d)
        m = u if i % 2 == 0 else v
        y = int.from_bytes(s, "big")
        c = (_num_radix(b_half, radix) - y) % (radix**m)
        c_digits = _str_m_radix(c, radix, m)
        b_half, a = a, c_digits
    return a + b_half


def _validate(radix: int, length: int, tweak: bytes) -> None:
    if not (_MIN_RADIX <= radix <= _MAX_RADIX):
        raise SurrogateDomainError(
            f"FF1 radix {radix} is outside the supported range [{_MIN_RADIX}, {_MAX_RADIX}]"
        )
    if length < _MIN_LENGTH:
        raise SurrogateDomainError(
            f"FF1 digit-list length {length} is below the minimum of {_MIN_LENGTH} — "
            "FF1 requires at least two digits to split into two Feistel halves"
        )
    if len(tweak) > _MAX_TWEAK_LENGTH:
        raise SurrogateDomainError("FF1 tweak exceeds the maximum supported length")


def _feistel_params(radix: int, digits_length: int, tweak: bytes) -> tuple[int, int, int, int]:
    """Return `(u, v, b, d)`: the two Feistel half-lengths, the byte
    width used to encode a half's numeric value in `Q`, and the PRF
    output length — all derived once per call, per NIST SP 800-38G
    steps 1, 3, and 4, and reused unchanged across every round."""
    n = digits_length
    u = n // 2
    v = n - u
    b = math.ceil(math.ceil(v * math.log2(radix)) / 8)
    d = 4 * math.ceil(b / 4) + 4
    return u, v, b, d


def _num_radix(digits: list[int], radix: int) -> int:
    """NUM_radix(X): `digits` (most significant first, each in
    `[0, radix)`) interpreted as a base-`radix` integer."""
    value = 0
    for digit in digits:
        value = value * radix + digit
    return value


def _str_m_radix(value: int, radix: int, length: int) -> list[int]:
    """STR_m_radix(x): the `length`-digit base-`radix` representation
    of `value`, most significant first, left-zero-padded."""
    digits = [0] * length
    for i in range(length - 1, -1, -1):
        digits[i] = value % radix
        value //= radix
    return digits


def _build_p(radix: int, u: int, n: int, t: int) -> bytes:
    """The round-independent 16-byte prefix mixed into every PRF call
    — fixes `radix`, `NUMrnds` (=10), `u`, `n`, and the tweak length
    `t` into the permutation, so different domain shapes can never
    collide under the same key."""
    return (
        bytes([1, 2, 1])
        + radix.to_bytes(3, "big")
        + bytes([_ROUNDS])
        + bytes([u % 256])
        + n.to_bytes(4, "big")
        + t.to_bytes(4, "big")
    )


def _build_q(tweak: bytes, b: int, round_index: int, digits: list[int], radix: int) -> bytes:
    """The per-round PRF input suffix: the tweak, zero-padded so
    `P || Q` lands on a 16-byte boundary, the round index, and the
    numeric value of whichever Feistel half this round consumes."""
    pad_len = (-len(tweak) - b - 1) % 16
    return (
        tweak + bytes(pad_len) + bytes([round_index]) + _num_radix(digits, radix).to_bytes(b, "big")
    )


def _prf(key: bytes, data: bytes) -> bytes:
    """PRF(X): AES-CBC-MAC with a zero IV over `data` (already a
    multiple of 16 bytes by construction) — the final ciphertext block
    only."""
    encryptor = Cipher(algorithms.AES(key), modes.CBC(b"\x00" * 16)).encryptor()
    ciphertext = encryptor.update(data) + encryptor.finalize()
    return ciphertext[-16:]


def _generate_s(key: bytes, r: bytes, d: int) -> bytes:
    """S: `d` bytes, extending `R` with `CIPH_K(R XOR [j])` blocks
    (`j` = 1, 2, ...) for as long as `R` alone falls short of `d`
    bytes, then truncated to exactly `d`."""
    s = r
    counter = 1
    while len(s) < d:
        block = _xor_bytes(r, counter.to_bytes(16, "big"))
        encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
        s += encryptor.update(block) + encryptor.finalize()
        counter += 1
    return s[:d]


def _xor_bytes(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b, strict=True))
