"""Aadhaar (Indian national ID) detector — canonical form, Verhoeff-gated."""

import re
from typing import Final

from src.core.types import EntityType, Offset, Span, Tier
from src.detect.tier1.checksum import verhoeff_is_valid

_CANDIDATE_PATTERN: Final[re.Pattern[str]] = re.compile(r"\b\d{12}\b")
"""Matches an isolated 12-digit run — a canonical, unobfuscated Aadhaar
candidate. Spaced (`1234 5678 9012`), dashed, or otherwise obfuscated
forms are a measured detection gap, not an oversight here: Tier 1 is
only ever described as guaranteed "if the entity is present in a
canonical, unobfuscated form" (ARCHITECTURE.md, Tier 1 — deterministic).
Obfuscated forms are the adversarial suite's concern (Phase 6), not
this detector's.
"""


class AadhaarDetector:
    """Detects canonical-form Aadhaar numbers, Verhoeff-validated.

    Regex extracts every isolated 12-digit run; Verhoeff decides which
    are real evidence. This ordering is deliberate: "regex alone
    produces false positives on any 12-digit number; the checksum is
    what converts a guess into evidence" (ARCHITECTURE.md, Tier 1).
    """

    entity_type: EntityType = "AADHAAR"
    tier: Tier = 1

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for match in _CANDIDATE_PATTERN.finditer(text):
            if verhoeff_is_valid(match.group()):
                spans.append(
                    Span(
                        start=Offset(match.start()),
                        end=Offset(match.end()),
                        entity_type=self.entity_type,
                        tier=self.tier,
                    )
                )
        return spans
