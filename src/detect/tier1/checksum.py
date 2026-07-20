"""Checksum algorithms for Tier-1 structured entities.

The single implementation of Verhoeff (Aadhaar) and Luhn (payment
card): CLAUDE.md, No duplicated logic — "Checksum validation ... exists
once. If a detector and a benchmark generator both need Verhoeff, they
import the same function — a benchmark that validates with a second
implementation is measuring the second implementation." The Phase 5
benchmark generator imports this module rather than reimplementing
either algorithm.

Both algorithms expose a `*_is_valid` predicate (used by detectors, to
decide whether a regex candidate is real evidence) and a
`*_generate_check_digit` function (used by whichever code needs to
construct a valid number from a payload — the Phase 2 Task 5 FF1
surrogate engine and the Phase 5 benchmark generator; not consumed by
this task, but kept alongside validation because the two are the same
arithmetic run in opposite directions, and splitting them across
modules would be the duplication this docstring just argued against).
"""

from typing import Final

_VERHOEFF_D_TABLE: Final[tuple[tuple[int, ...], ...]] = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
"""Verhoeff's dihedral group D5 multiplication table (Verhoeff, J.,
1969, "Error Detecting Decimal Codes")."""

_VERHOEFF_P_TABLE: Final[tuple[tuple[int, ...], ...]] = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)
"""Verhoeff's digit-permutation table, applied at position `i % 8`."""

_VERHOEFF_INV_TABLE: Final[tuple[int, ...]] = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)
"""Verhoeff's inverse table, used to derive a check digit that drives
the running checksum to 0."""


def _verhoeff_checksum(digits: str) -> int:
    """Run the Verhoeff algorithm over `digits`, most-significant digit
    first, returning the final checksum register value (0 iff the
    number — including its own last digit as the check digit —
    validates)."""
    checksum = 0
    for i, char in enumerate(reversed(digits)):
        checksum = _VERHOEFF_D_TABLE[checksum][_VERHOEFF_P_TABLE[i % 8][int(char)]]
    return checksum


def verhoeff_is_valid(number: str) -> bool:
    """True iff `number` is all-digit and its last digit is a valid
    Verhoeff check digit for the digits preceding it.

    Verhoeff detects all single-digit substitution errors and all
    adjacent-transposition errors, which is why UIDAI uses it for the
    Aadhaar check digit rather than a simpler scheme (References,
    ARCHITECTURE.md). Any non-digit input is invalid, not an error —
    a regex candidate that happens to contain a non-digit is exactly
    the "near miss" this predicate exists to reject.
    """
    if not number.isdigit():
        return False
    return _verhoeff_checksum(number) == 0


def verhoeff_generate_check_digit(payload: str) -> str:
    """Return the single Verhoeff check digit for `payload`.

    `payload` is the number *without* its check digit — for a 12-digit
    Aadhaar this is the 11-digit body. Appending the returned digit to
    `payload` always yields a string for which `verhoeff_is_valid` is
    true; this is the same table walk as validation, offset by one
    position, which is why the two functions live side by side.

    Raises:
        ValueError: `payload` is not all-digit — there is no check
            digit for a non-numeric body.
    """
    if not payload.isdigit():
        raise ValueError(
            f"cannot compute a Verhoeff check digit for a non-digit payload of "
            f"length {len(payload)}"
        )
    checksum = 0
    for i, char in enumerate(reversed(payload)):
        checksum = _VERHOEFF_D_TABLE[checksum][_VERHOEFF_P_TABLE[(i + 1) % 8][int(char)]]
    return str(_VERHOEFF_INV_TABLE[checksum])


def luhn_is_valid(number: str) -> bool:
    """True iff `number` is all-digit, at least two digits long, and
    satisfies the Luhn (mod 10) checksum (ISO/IEC 7812-1) — the payment
    card check-digit scheme.

    Doubling starts from the digit immediately left of the last
    (check) digit, counting from the right — index 1 in the
    right-to-left enumeration below.
    """
    if not number.isdigit() or len(number) < 2:
        return False
    total = 0
    for i, char in enumerate(reversed(number)):
        digit = int(char)
        if i % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def luhn_generate_check_digit(payload: str) -> str:
    """Return the single Luhn check digit for `payload`.

    `payload` is the card number *without* its check digit. Doubling
    here starts from the rightmost digit of `payload` (index 0), which
    becomes index 1 — the first doubled position — once the check
    digit is appended to its right; this is the same offset-by-one
    relationship as `verhoeff_generate_check_digit` vs
    `verhoeff_is_valid`.

    Raises:
        ValueError: `payload` is not all-digit.
    """
    if not payload.isdigit():
        raise ValueError(
            f"cannot compute a Luhn check digit for a non-digit payload of "
            f"length {len(payload)}"
        )
    total = 0
    for i, char in enumerate(reversed(payload)):
        digit = int(char)
        if i % 2 == 0:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return str((10 - (total % 10)) % 10)
