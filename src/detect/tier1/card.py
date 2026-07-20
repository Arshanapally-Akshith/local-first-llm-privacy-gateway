"""Payment card detector — canonical form, Luhn-gated."""

import re
from typing import Final

from src.core.types import EntityType, Offset, Span, Tier
from src.detect.tier1.checksum import luhn_is_valid

_CANDIDATE_PATTERN: Final[re.Pattern[str]] = re.compile(r"\b\d{12,19}\b")
"""Matches an isolated 12-to-19-digit run — ISO/IEC 7812's card-number
length range. Spaced (`4111 1111 1111 1111`) or dashed forms are a
measured detection gap here, not an oversight — see the same reasoning
in `aadhaar.py`; obfuscation is the adversarial suite's concern
(Phase 6).
"""


class CardDetector:
    """Detects canonical-form payment card numbers, Luhn-validated.

    Regex extracts every isolated 12-19 digit run; Luhn decides which
    are real evidence, for the same reason Verhoeff gates Aadhaar
    candidates: an unvalidated digit run of card-number length is a
    guess, not evidence.
    """

    entity_type: EntityType = "CARD"
    tier: Tier = 1

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for match in _CANDIDATE_PATTERN.finditer(text):
            if luhn_is_valid(match.group()):
                spans.append(
                    Span(
                        start=Offset(match.start()),
                        end=Offset(match.end()),
                        entity_type=self.entity_type,
                        tier=self.tier,
                    )
                )
        return spans
