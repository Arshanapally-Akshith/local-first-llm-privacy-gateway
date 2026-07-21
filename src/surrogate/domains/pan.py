"""PAN surrogate domain.

PAN's format mixes letters and digits (`AAAPL1234C`): 5 free letter
positions (0, 1, 2, 4, 9) and 4 free digit positions (5-8), combined
via `mixed_radix_ff1.py` into one domain of size `26**5 * 10**4`
(~1.19x10^11) — comfortably above NIST's recommended minimum, which
the 4 free digit positions alone (`10**4`) would not clear on their
own (ARCHITECTURE.md's "10-16 digit domains, not short fields"
caveat, made concrete).

Position 3 (the holder-category letter — `PanDetector`'s own
structural check) is frozen, copied verbatim: permuting it could
produce a category value outside the Income Tax Department's 10
documented codes. Position 9 (PAN's 10th character) has no publicly
documented computation — `PanDetector` never validated it either — so
it is simply another free letter position here, permuted like any
other; there is nothing to "repair" it to.
"""

from typing import Final

from src.core.exceptions import SurrogateDomainError
from src.core.types import EntityType
from src.surrogate import mixed_radix_ff1

_TWEAK: Final[bytes] = b"PAN"
_LENGTH: Final[int] = 10
_FREE_LETTER_POSITIONS: Final[tuple[int, ...]] = (0, 1, 2, 4, 9)
_FROZEN_CATEGORY_POSITION: Final[int] = 3
_FREE_DIGIT_POSITIONS: Final[tuple[int, ...]] = (5, 6, 7, 8)
_RADIXES: Final[tuple[int, ...]] = (26,) * len(_FREE_LETTER_POSITIONS) + (10,) * len(
    _FREE_DIGIT_POSITIONS
)


class PanDomain:
    entity_type: EntityType = "PAN"
    max_surrogate_length: int = _LENGTH
    """Always exactly 10 characters — PAN has no variable-length shape."""

    def encrypt(self, value: str, key: bytes) -> str:
        _validate(value)
        symbols = _extract_free_symbols(value)
        permuted = mixed_radix_ff1.encrypt_combined(key, _TWEAK, symbols, _RADIXES)
        return _rebuild(permuted, frozen_category=value[_FROZEN_CATEGORY_POSITION])

    def decrypt(self, surrogate: str, key: bytes) -> str:
        _validate(surrogate)
        symbols = _extract_free_symbols(surrogate)
        original = mixed_radix_ff1.decrypt_combined(key, _TWEAK, symbols, _RADIXES)
        return _rebuild(original, frozen_category=surrogate[_FROZEN_CATEGORY_POSITION])


def _validate(value: str) -> None:
    if len(value) != _LENGTH:
        raise SurrogateDomainError(
            f"PanDomain expected a {_LENGTH}-character value, got length {len(value)}"
        )
    letters = [value[i] for i in (*_FREE_LETTER_POSITIONS, _FROZEN_CATEGORY_POSITION)]
    digits = [value[i] for i in _FREE_DIGIT_POSITIONS]
    if not all("A" <= c <= "Z" for c in letters) or not all(c.isdigit() for c in digits):
        raise SurrogateDomainError(
            "PanDomain expected 6 uppercase letters and 4 digits at fixed positions"
        )


def _extract_free_symbols(value: str) -> list[int]:
    letters = [ord(value[i]) - ord("A") for i in _FREE_LETTER_POSITIONS]
    digits = [int(value[i]) for i in _FREE_DIGIT_POSITIONS]
    return letters + digits


def _rebuild(symbols: list[int], *, frozen_category: str) -> str:
    letters = symbols[: len(_FREE_LETTER_POSITIONS)]
    digits = symbols[len(_FREE_LETTER_POSITIONS) :]
    chars = [""] * _LENGTH
    for position, letter_value in zip(_FREE_LETTER_POSITIONS, letters, strict=True):
        chars[position] = chr(ord("A") + letter_value)
    chars[_FROZEN_CATEGORY_POSITION] = frozen_category
    for position, digit_value in zip(_FREE_DIGIT_POSITIONS, digits, strict=True):
        chars[position] = str(digit_value)
    return "".join(chars)
