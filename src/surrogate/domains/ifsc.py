"""IFSC surrogate domain.

4 free letter positions (bank code, radix 26 each) combined with 6
free alphanumeric positions (branch code, radix 36 each — each
position may independently be a letter or a digit) via
`mixed_radix_ff1.py`, giving a combined domain of `26**4 * 36**6`
(~9.95x10^14) — the bank-code segment alone (`26**4` ≈ 456,976) falls
just short of NIST's recommended minimum on its own, the same
short-field caveat PAN's digit segment runs into.

Position 4 (always the literal `'0'` — RBI reserves it) is frozen,
copied verbatim, never part of the permuted domain at all.
"""

from typing import Final

from src.core.exceptions import SurrogateDomainError
from src.core.types import EntityType
from src.surrogate import mixed_radix_ff1

_TWEAK: Final[bytes] = b"IFSC"
_LENGTH: Final[int] = 11
_BANK_CODE_POSITIONS: Final[tuple[int, ...]] = (0, 1, 2, 3)
_FROZEN_LITERAL_POSITION: Final[int] = 4
_FROZEN_LITERAL: Final[str] = "0"
_BRANCH_CODE_POSITIONS: Final[tuple[int, ...]] = (5, 6, 7, 8, 9, 10)
_RADIXES: Final[tuple[int, ...]] = (26,) * len(_BANK_CODE_POSITIONS) + (36,) * len(
    _BRANCH_CODE_POSITIONS
)


class IfscDomain:
    entity_type: EntityType = "IFSC"

    def encrypt(self, value: str, key: bytes) -> str:
        _validate(value)
        symbols = _extract_free_symbols(value)
        permuted = mixed_radix_ff1.encrypt_combined(key, _TWEAK, symbols, _RADIXES)
        return _rebuild(permuted)

    def decrypt(self, surrogate: str, key: bytes) -> str:
        _validate(surrogate)
        symbols = _extract_free_symbols(surrogate)
        original = mixed_radix_ff1.decrypt_combined(key, _TWEAK, symbols, _RADIXES)
        return _rebuild(original)


def _validate(value: str) -> None:
    if len(value) != _LENGTH:
        raise SurrogateDomainError(
            f"IfscDomain expected a {_LENGTH}-character value, got length {len(value)}"
        )
    bank_code = [value[i] for i in _BANK_CODE_POSITIONS]
    branch_code = [value[i] for i in _BRANCH_CODE_POSITIONS]
    if (
        value[_FROZEN_LITERAL_POSITION] != _FROZEN_LITERAL
        or not all("A" <= c <= "Z" for c in bank_code)
        or not all(_alphanumeric_value(c) is not None for c in branch_code)
    ):
        raise SurrogateDomainError(
            "IfscDomain expected 4 uppercase letters, a literal '0', and 6 alphanumeric characters"
        )


def _alphanumeric_value(char: str) -> int | None:
    """`0`-`9` -> 0-9, `A`-`Z` -> 10-35 (radix-36); `None` if `char`
    is neither."""
    if char.isdigit():
        return int(char)
    if "A" <= char <= "Z":
        return ord(char) - ord("A") + 10
    return None


def _alphanumeric_char(value: int) -> str:
    return str(value) if value < 10 else chr(ord("A") + value - 10)


def _extract_free_symbols(value: str) -> list[int]:
    bank_code = [ord(value[i]) - ord("A") for i in _BANK_CODE_POSITIONS]
    branch_code = [
        symbol
        for i in _BRANCH_CODE_POSITIONS
        if (symbol := _alphanumeric_value(value[i])) is not None
    ]
    return bank_code + branch_code


def _rebuild(symbols: list[int]) -> str:
    bank_code = symbols[: len(_BANK_CODE_POSITIONS)]
    branch_code = symbols[len(_BANK_CODE_POSITIONS) :]
    chars = [""] * _LENGTH
    for position, letter_value in zip(_BANK_CODE_POSITIONS, bank_code, strict=True):
        chars[position] = chr(ord("A") + letter_value)
    chars[_FROZEN_LITERAL_POSITION] = _FROZEN_LITERAL
    for position, symbol_value in zip(_BRANCH_CODE_POSITIONS, branch_code, strict=True):
        chars[position] = _alphanumeric_char(symbol_value)
    return "".join(chars)
