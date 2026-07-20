"""Email address detector."""

import re
from typing import Final

from src.core.types import EntityType, Offset, Span, Tier

_CANDIDATE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9.-])"
)
"""Matches an isolated `local@domain.tld`-shaped token: a pragmatic,
simplified pattern (RFC 5322's full grammar is far larger than this
project needs, and Presidio's own default recognizer makes the same
simplification) requiring at least one dot-separated TLD of 2+ letters
after `@`.

Lookaround boundaries, not `\\b`, for the same reason as
`upi.py` — the local-part alphabet mixes word and non-word characters.
Requiring a dot in the domain (`UpiDetector` requires the opposite) is
what keeps this detector from claiming a UPI ID as an email; see
`upi.py`'s docstring for the other half of that boundary.
"""


class EmailDetector:
    """Detects canonical, unobfuscated email addresses only.

    No checksum applies to an email address; the structural
    requirement — a dot-separated TLD — is encoded directly in the
    candidate pattern.

    Contract: detects canonical, unobfuscated forms only. Does not
    perform OCR correction, spacing normalization, Unicode
    normalization, or adversarial-obfuscation handling — those are
    the Phase 6 adversarial suite's concern, not this detector's.
    """

    entity_type: EntityType = "EMAIL"
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
