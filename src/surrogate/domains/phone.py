"""Indian mobile phone surrogate domain.

The detector's candidate pattern (`src/detect/tier1/phone.py`) accepts
a bare 10-digit number or one with an attached `+91`/`91`/`0` prefix;
this domain strips and remembers that prefix (frozen, copied
verbatim — it carries no information about the specific subscriber),
then treats the 10-digit core the same way: the leading digit (only
ever `6`-`9`, already public knowledge about *any* Indian mobile
number) is frozen too, and the remaining 9 digits are FF1-permuted
(radix 10, `10**9` — above NIST's recommended minimum on its own, no
mixed-radix combination needed). No checksum exists for phone
numbers, so there is nothing to repair after permuting.
"""

from typing import Final

from src.core.exceptions import SurrogateDomainError
from src.core.types import EntityType
from src.surrogate import ff1

_TWEAK: Final[bytes] = b"PHONE"
_CORE_LENGTH: Final[int] = 10
_VALID_LEADING_DIGITS: Final[frozenset[str]] = frozenset("6789")


class PhoneDomain:
    entity_type: EntityType = "PHONE"

    def encrypt(self, value: str, key: bytes) -> str:
        prefix, core = _split_prefix(value)
        free_digits = [int(c) for c in core[1:]]
        permuted = ff1.ff1_encrypt(key, _TWEAK, 10, free_digits)
        return prefix + core[0] + "".join(str(d) for d in permuted)

    def decrypt(self, surrogate: str, key: bytes) -> str:
        prefix, core = _split_prefix(surrogate)
        free_digits = [int(c) for c in core[1:]]
        original = ff1.ff1_decrypt(key, _TWEAK, 10, free_digits)
        return prefix + core[0] + "".join(str(d) for d in original)


def _split_prefix(value: str) -> tuple[str, str]:
    """Length alone determines the prefix unambiguously: a bare core
    is exactly 10 digits, and each prefix adds a fixed number of
    characters — see `phone.py`'s detector, whose candidate pattern
    only ever produces these four shapes."""
    if value.startswith("+91") and len(value) == 13:
        prefix, core = "+91", value[3:]
    elif value.startswith("91") and len(value) == 12:
        prefix, core = "91", value[2:]
    elif value.startswith("0") and len(value) == 11:
        prefix, core = "0", value[1:]
    elif len(value) == 10:
        prefix, core = "", value
    else:
        raise SurrogateDomainError(
            f"PhoneDomain could not determine a prefix for a value of length {len(value)}"
        )
    if not core.isdigit() or core[0] not in _VALID_LEADING_DIGITS:
        raise SurrogateDomainError("PhoneDomain expected a 10-digit core starting with 6-9")
    return prefix, core
