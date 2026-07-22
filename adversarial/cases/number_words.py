"""Bypass class 2/9: number-words (BUILD.md/ARCHITECTURE.md's B2,
`"nine eight seven six"`).

Mechanism: identical root cause to `spaced_digits.py` — every numeric
Tier-1 candidate pattern requires a contiguous digit run, and spelling
each digit out as an English word removes every digit character from
the text entirely, which is a strict superset of what spacing alone
defeats.

Coverage
--------
Exercised: AADHAAR, CARD, PHONE — same rationale as `spaced_digits.py`
(pure digit-run canonical forms).

Intentionally omitted: PAN, IFSC, VEHICLE_REG, UPI, EMAIL, PERSON, ORG,
ADDRESS — same reasoning as `spaced_digits.py`'s own Coverage section;
number-spelling is specifically a digit-run obfuscation and has no
analogue for mixed-alphanumeric or free-text types.
"""

import random
from typing import Final

from src.core.types import EntityType

from adversarial.cases.carrier import build_slot_case
from adversarial.cases.case_types import AdversarialCase
from benchmarks.generate.entity_values import generate_value

_SEED: Final[int] = 60602

_ENTITY_TYPES: Final[tuple[EntityType, ...]] = ("AADHAAR", "CARD", "PHONE")

_DIGIT_WORDS: Final[dict[str, str]] = {
    "0": "zero",
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
}

_PREFIX: Final[str] = "The number is spelled out as "
_SUFFIX: Final[str] = " for the voice transcript."


def _spelled_out(value: str) -> str:
    return " ".join(_DIGIT_WORDS[digit] for digit in value if digit.isdigit())


def build_cases() -> list[AdversarialCase]:
    rng = random.Random(_SEED)
    cases: list[AdversarialCase] = []
    for entity_type in _ENTITY_TYPES:
        value = generate_value(entity_type, rng)
        cases.append(
            build_slot_case(
                case_id=f"number_words-{entity_type}-clean",
                bypass_class="number_words",
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
                case_id=f"number_words-{entity_type}-adversarial",
                bypass_class="number_words",
                entity_type=entity_type,
                label="adversarial",
                prefix=_PREFIX,
                embedded_value=_spelled_out(value),
                suffix=_SUFFIX,
                real_value=value,
                expected_outcome="leaked",
            )
        )
    return cases
