"""PAN (Indian Income Tax Permanent Account Number) detector."""

import re
from typing import Final

from src.core.types import EntityType, Offset, Span, Tier

_CANDIDATE_PATTERN: Final[re.Pattern[str]] = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
"""Matches an isolated 10-character PAN-shaped token: 5 letters, 4
digits, 1 letter — canonical, unobfuscated, uppercase form only.
Spaced/lowercase/OCR-noisy forms are out of scope for this detector
(see class docstring)."""

PAN_CATEGORY_LETTERS: Final[frozenset[str]] = frozenset("PCHABGJLFT")
"""The Income Tax Department's documented 4th-character holder-category
codes (Individual, Company, HUF, AOP, BOI, Government, Artificial
Judicial Person, Local Authority, Firm/LLP, Trust). Unlike Aadhaar/Card,
PAN has no published arithmetic check digit — this membership check is
the structural equivalent: it is what separates real evidence from any
5-letters+4-digits+1-letter string, the same role Verhoeff/Luhn play
for Aadhaar/Card.

Public (not module-private) so the Phase 5 benchmark generator
(`benchmarks/generate/entity_values.py`) can construct synthetic,
structurally-valid PANs from the same documented set this detector
validates against, rather than restating the ten letters as a second,
driftable copy (CLAUDE.md: "no duplicated logic")."""


class PanDetector:
    """Detects canonical, unobfuscated PAN numbers only.

    Regex extracts every isolated PAN-shaped token; the 4th-character
    category check decides which are real evidence, the same
    candidate-then-validate shape as `AadhaarDetector`/`CardDetector`,
    with a structural check standing in for a checksum PAN does not
    have.

    Contract: detects canonical, unobfuscated forms only. Does not
    perform OCR correction, spacing normalization, Unicode
    normalization, or adversarial-obfuscation handling — those are
    the Phase 6 adversarial suite's concern, not this detector's.
    """

    entity_type: EntityType = "PAN"
    tier: Tier = 1

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for match in _CANDIDATE_PATTERN.finditer(text):
            candidate = match.group()
            if candidate[3] in PAN_CATEGORY_LETTERS:
                spans.append(
                    Span(
                        start=Offset(match.start()),
                        end=Offset(match.end()),
                        entity_type=self.entity_type,
                        tier=self.tier,
                    )
                )
        return spans
