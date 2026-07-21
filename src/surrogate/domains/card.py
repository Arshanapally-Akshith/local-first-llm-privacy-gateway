"""Payment card surrogate domain.

FF1-permutes every digit except the last (radix 10, payload length
`len(value) - 1`; for the shortest accepted card length, 12 digits,
that's `10**11`, well above NIST's recommended minimum — no
mixed-radix combination needed). The last digit is re-derived via
Luhn on each side, reusing `src/detect/tier1/checksum.py`'s single
implementation.
"""

from typing import Final

from src.core.exceptions import SurrogateDomainError
from src.core.types import EntityType
from src.detect.tier1.checksum import luhn_generate_check_digit
from src.surrogate import ff1

_TWEAK: Final[bytes] = b"CARD"
_MIN_LENGTH: Final[int] = 12
_MAX_LENGTH: Final[int] = 19


class CardDomain:
    entity_type: EntityType = "CARD"
    max_surrogate_length: int = _MAX_LENGTH
    """19 digits — the longest card length this domain accepts
    (ISO/IEC 7812-1 allows 12-19 digit PANs); `decrypt()` always
    produces a surrogate the same length as its input, so this domain's
    own upper bound is the true worst case, not an average."""

    def encrypt(self, value: str, key: bytes) -> str:
        payload = _validate_and_split(value)
        permuted = ff1.ff1_encrypt(key, _TWEAK, 10, payload)
        payload_str = "".join(str(d) for d in permuted)
        return payload_str + luhn_generate_check_digit(payload_str)

    def decrypt(self, surrogate: str, key: bytes) -> str:
        payload = _validate_and_split(surrogate)
        original = ff1.ff1_decrypt(key, _TWEAK, 10, payload)
        payload_str = "".join(str(d) for d in original)
        return payload_str + luhn_generate_check_digit(payload_str)


def _validate_and_split(value: str) -> list[int]:
    if not (_MIN_LENGTH <= len(value) <= _MAX_LENGTH) or not value.isdigit():
        raise SurrogateDomainError(
            f"CardDomain expected a {_MIN_LENGTH}-{_MAX_LENGTH} digit value, "
            f"got length {len(value)}"
        )
    return [int(c) for c in value[:-1]]
