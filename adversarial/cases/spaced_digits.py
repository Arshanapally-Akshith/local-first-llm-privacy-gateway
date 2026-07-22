"""Bypass class 1/9: spaced digits (BUILD.md, ARCHITECTURE.md's B1).

Mechanism, verified empirically before this module was written (not
assumed): every numeric Tier-1 candidate pattern requires a contiguous
digit run — `\\b\\d{12}\\b` (AADHAAR), `\\b\\d{12,19}\\b` (CARD), and
the phone pattern's own `[6-9]\\d{9}` core (`src/detect/tier1/aadhaar.py`,
`card.py`, `phone.py`) — so grouping the same digits with ordinary
spaces (`"9999 1234 5676"`) removes the one contiguous run every
pattern needs and defeats detection entirely, not partially.

Coverage
--------
Exercised: AADHAAR, CARD, PHONE — the three Tier-1 types whose
canonical form is a pure, undifferentiated digit run of fixed or
bounded length, which is exactly what spacing disrupts.

Intentionally omitted: PAN, IFSC, VEHICLE_REG (mixed letter/digit
canonical forms — "spacing digits" has no direct analogue when the
format already alternates character classes; a distinct obfuscation,
not covered by this class); UPI, EMAIL (delimiter-structured local-part
and domain, not a pure digit run); PERSON, ORG, ADDRESS (free text, not
digit-based at all — see `transliterated_names.py` for this suite's one
Tier-2 bypass class).
"""

import random
from typing import Final

from src.core.types import EntityType

from adversarial.cases.carrier import build_slot_case
from adversarial.cases.case_types import AdversarialCase
from benchmarks.generate.entity_values import generate_value

_SEED: Final[int] = 60601
"""Arbitrary, fixed seed — determinism (CLAUDE.md), not a measured
value; chosen once and never changed, same convention as
`benchmarks/generate`'s own seeding."""

_ENTITY_TYPES: Final[tuple[EntityType, ...]] = ("AADHAAR", "CARD", "PHONE")
_GROUP_SIZE: Final[int] = 4
"""Digits per group in the obfuscated form (`"9999 1234 5676"`) — a
common, plausible spacing convention; the mechanism is unaffected by
the exact group size, since any space at all breaks the required
contiguous run."""

_PREFIX: Final[str] = "Please note the reference number "
_SUFFIX: Final[str] = " for your records."


def _spaced(value: str) -> str:
    return " ".join(value[i : i + _GROUP_SIZE] for i in range(0, len(value), _GROUP_SIZE))


def build_cases() -> list[AdversarialCase]:
    rng = random.Random(_SEED)
    cases: list[AdversarialCase] = []
    for entity_type in _ENTITY_TYPES:
        value = generate_value(entity_type, rng)
        cases.append(
            build_slot_case(
                case_id=f"spaced_digits-{entity_type}-clean",
                bypass_class="spaced_digits",
                entity_type=entity_type,
                label="clean",
                prefix=_PREFIX,
                embedded_value=value,
                suffix=_SUFFIX,
                real_value=value,
                expected_outcome="caught",
            )
        )
        cases.append(
            build_slot_case(
                case_id=f"spaced_digits-{entity_type}-adversarial",
                bypass_class="spaced_digits",
                entity_type=entity_type,
                label="adversarial",
                prefix=_PREFIX,
                embedded_value=_spaced(value),
                suffix=_SUFFIX,
                real_value=value,
                expected_outcome="leaked",
            )
        )
    return cases
