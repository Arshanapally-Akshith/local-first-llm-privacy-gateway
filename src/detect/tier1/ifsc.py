"""IFSC (RBI Indian Financial System Code) detector."""

import re
from typing import Final

from src.core.types import EntityType, Offset, Span, Tier

_CANDIDATE_PATTERN: Final[re.Pattern[str]] = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")
"""Matches an isolated 11-character IFSC-shaped token: 4-letter bank
code, a literal `0` (RBI reserves the 5th character for future use and
always sets it to zero today), 6-character alphanumeric branch code —
canonical, unobfuscated, uppercase form only.

The 5th-character constraint is a fixed literal, not a multi-value
membership set the way PAN's category letter is, so it is encoded
directly in the pattern rather than a separate validation predicate —
there is nothing left to structurally check once the regex matches."""


class IfscDetector:
    """Detects canonical, unobfuscated IFSC codes only.

    IFSC has no published arithmetic check digit; the reserved literal
    `0` at position 5 is the only structural fact beyond length and
    character class, and it is already enforced by the candidate
    pattern itself.

    Contract: detects canonical, unobfuscated forms only. Does not
    perform OCR correction, spacing normalization, Unicode
    normalization, or adversarial-obfuscation handling — those are
    the Phase 6 adversarial suite's concern, not this detector's.
    """

    entity_type: EntityType = "IFSC"
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
