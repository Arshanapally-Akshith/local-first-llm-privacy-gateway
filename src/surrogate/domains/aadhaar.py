"""Aadhaar surrogate domain.

FF1-permutes the 11-digit payload (radix 10 — `10**11` well above
NIST's recommended minimum, no mixed-radix combination needed); the
12th digit is never permuted directly, it is re-derived via Verhoeff
on each side, reusing `src/detect/tier1/checksum.py`'s single
implementation (CLAUDE.md: "one Verhoeff, one FF1").

Does **not** enforce UIDAI's reserved-range requirement, and never
will: `docs/DECISIONS.md` (2026-07-20, "Aadhaar reserved-range
requirement retired as mathematically unsatisfiable") proves no
deterministic, stateless, invertible construction can guarantee this
for any reserved range — a pigeonhole argument independent of
technique, not a gap specific to this module's cycle-walking attempt.
Every surrogate produced here is Verhoeff-valid and round-trips
correctly; the residual — a surrogate's shape may coincide with an
issuable number pattern — is a permanent, documented property of this
domain, not a TODO.
"""

from typing import Final

from src.core.exceptions import SurrogateDomainError
from src.core.types import EntityType
from src.detect.tier1.checksum import verhoeff_generate_check_digit
from src.surrogate import ff1

_TWEAK: Final[bytes] = b"AADHAAR"
_PAYLOAD_LENGTH: Final[int] = 11
_LENGTH: Final[int] = 12


class AadhaarDomain:
    entity_type: EntityType = "AADHAAR"

    def encrypt(self, value: str, key: bytes) -> str:
        payload = _validate_and_split(value)
        permuted = ff1.ff1_encrypt(key, _TWEAK, 10, payload)
        payload_str = "".join(str(d) for d in permuted)
        return payload_str + verhoeff_generate_check_digit(payload_str)

    def decrypt(self, surrogate: str, key: bytes) -> str:
        payload = _validate_and_split(surrogate)
        original = ff1.ff1_decrypt(key, _TWEAK, 10, payload)
        payload_str = "".join(str(d) for d in original)
        return payload_str + verhoeff_generate_check_digit(payload_str)


def _validate_and_split(value: str) -> list[int]:
    if len(value) != _LENGTH or not value.isdigit():
        raise SurrogateDomainError(
            f"AadhaarDomain expected a {_LENGTH}-digit value, got length {len(value)}"
        )
    return [int(c) for c in value[:_PAYLOAD_LENGTH]]
