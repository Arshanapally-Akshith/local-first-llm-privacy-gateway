"""Indian vehicle registration mark detector."""

import re
from typing import Final

from src.core.types import EntityType, Offset, Span, Tier

_CANDIDATE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:[A-Z]{2}\d{1,2}[A-Z]{1,3}\d{4}|\d{2}BH\d{4}[A-Z]{1,2})\b"
)
"""Matches an isolated, canonical-form registration mark under either
scheme in current use:

- the state-code scheme (e.g. `KA01AB1234`): 2-letter state code,
  1-2 digit RTO/district code, 1-3 letter series, 4-digit number;
- the BH ("Bharat") series introduced in 2021 (e.g. `23BH1234AB`):
  2-digit year of registration, literal `BH`, 4-digit number,
  1-2 letter suffix.

Deliberately no RTO state-code whitelist (e.g. requiring the 2-letter
prefix to be one of the ~85 real state/UT codes): that list is not
short, evolves, and reconstructing it from general knowledge without
a citable source would be exactly the unverified-claim-dressed-as-fact
this project's rules warn against. Structural regex only, at the same
rigor level as PAN and IFSC — format+structure, no semantic whitelist.
"""


class VehicleRegistrationDetector:
    """Detects canonical, unobfuscated vehicle registration marks only.

    No checksum applies to a registration mark; structure (state-code
    or BH-series shape) is the only available signal, and it is
    encoded directly in the candidate pattern.

    Contract: detects canonical, unobfuscated forms only. Does not
    perform OCR correction, spacing normalization, Unicode
    normalization, or adversarial-obfuscation handling — those are
    the Phase 6 adversarial suite's concern, not this detector's.
    """

    entity_type: EntityType = "VEHICLE_REG"
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
