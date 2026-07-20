"""UPI ID (NPCI Virtual Payment Address) detector."""

import re
from typing import Final

from src.core.types import EntityType, Offset, Span, Tier

_CANDIDATE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?<![A-Za-z0-9._-])[A-Za-z0-9._-]{2,256}@[A-Za-z][A-Za-z0-9]{1,64}(?![A-Za-z0-9.])"
)
"""Matches an isolated `handle@psp`-shaped token: a VPA local part
(alphanumeric plus `. _ -`, 2-256 chars per NPCI's documented range),
`@`, and a PSP handle (letters/digits, no dot).

Lookaround boundaries are used instead of `\\b`: the local-part
alphabet mixes word characters (letters, digits, `_`) with non-word
ones (`.`, `-`), so a plain `\\b` anchor would not reliably mark where
a real token starts or ends. The trailing `(?![A-Za-z0-9.])` is also
the mechanism that keeps this pattern from matching an email address:
a PSP handle never contains a dot, so `user@paytm` matches here but
`user@example.com` does not — the lookahead sees the `.` right after
`example` and rejects the candidate, leaving it for `EmailDetector`.
This is a deliberate, tested non-collision, not an accident of regex
priority.
"""


class UpiDetector:
    """Detects canonical, unobfuscated UPI IDs (VPAs) only.

    UPI IDs have no published checksum; NPCI's own structural
    constraint — a PSP handle contains no dot — is what the candidate
    pattern encodes and enforces, distinguishing a VPA from an email
    address by construction rather than a separate validation step.

    Contract: detects canonical, unobfuscated forms only. Does not
    perform OCR correction, spacing normalization, Unicode
    normalization, or adversarial-obfuscation handling — those are
    the Phase 6 adversarial suite's concern, not this detector's.
    """

    entity_type: EntityType = "UPI"
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
