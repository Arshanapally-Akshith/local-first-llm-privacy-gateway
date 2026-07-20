"""Indian mobile phone number detector."""

import re
from typing import Final

from src.core.types import EntityType, Offset, Span, Tier

_CANDIDATE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?<![A-Za-z0-9])(?:\+91|91|0)?[6-9]\d{9}(?![0-9])"
)
"""Matches an isolated 10-digit Indian mobile number (current TRAI
numbering: mobile numbers begin with 6, 7, 8, or 9), with an optional
`+91`, `91`, or `0` prefix directly attached — no spaced or dashed
prefix ("+91 98765 43210"), per this detector's canonical-form-only
contract.

Boundaries use explicit alphanumeric lookaround, not `\\b`: the
optional `+` prefix is a non-word character, so a plain `\\b` anchor
placed before it would not fire consistently the way it does for the
all-digit Aadhaar/Card patterns. The effect is the same as `\\b` for
this detector's purposes — a digit run glued directly to a letter
(`callme9876543210`) is rejected, matching `AadhaarDetector`'s and
`CardDetector`'s behaviour for the analogous case.

Scope: 10-digit mobile numbers only. Landline numbers (which use
variable-length STD area codes with no equivalent leading-digit
structural rule) are out of scope — a genuine coverage gap, not
silently unhandled, see this detector's class docstring.
"""


class PhoneDetector:
    """Detects canonical, unobfuscated Indian mobile numbers only.

    No checksum applies to a phone number; the only structural rule —
    a mobile number's first digit is 6-9 — is encoded directly in the
    candidate pattern's character class.

    Scope: mobile numbers only, optionally `+91`/`91`/`0`-prefixed
    with no separating space or dash. Landline numbers (STD-code
    format) are not detected — deliberately out of scope, not a bug,
    since they have no comparable structural signal to gate on without
    a country-wide STD-code table this project does not maintain.

    Contract: detects canonical, unobfuscated forms only. Does not
    perform OCR correction, spacing normalization, Unicode
    normalization, or adversarial-obfuscation handling — those are
    the Phase 6 adversarial suite's concern, not this detector's.
    """

    entity_type: EntityType = "PHONE"
    tier: Tier = 1

    def detect(self, text: str) -> list[Span]:
        return [
            Span(
                start=Offset(match.start()),
                end=Offset(match.end()),
                entity_type=self.entity_type,
                tier=self.tier,
            )
            for match in _CANDIDATE_PATTERN.finditer(text)
        ]
