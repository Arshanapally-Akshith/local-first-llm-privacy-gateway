"""Bypass class 5/9: zero-width characters (BUILD.md/ARCHITECTURE.md's
B9).

Mechanism, verified empirically before this module was written:
inserting U+200B (ZERO WIDTH SPACE) between every character of a
canonical value breaks the contiguous run every Tier-1 candidate
pattern requires, identical in kind to `spaced_digits.py` but with an
ordinary space swapped for an invisible one — confirmed directly:

    >>> import re
    >>> zw = "\\u200b"
    >>> re.findall(r"\\b\\d{12}\\b", zw.join("999912345676"))
    []
    >>> re.findall(r"\\b[A-Z]{5}\\d{4}[A-Z]\\b", zw.join("AAAPL1234C"))
    []

The one property that sets this class apart from `spaced_digits.py`
(worth stating explicitly, not just noting the mechanical overlap): the
obfuscation is invisible to a human reading the message, a log line, or
this suite's own results artifact — a reviewer skimming
`adversarial/results/latest.md` would see what looks like the intact
canonical value, not an obviously-spaced one, and would not notice
anything is wrong without inspecting the raw bytes. This is the
distinct, additional finding this class exists to surface, beyond "one
more way to break the contiguous-run assumption."

Coverage
--------
Exercised: AADHAAR, CARD, PAN — one pure-digit-run type, one
longer-digit-run type, and one mixed-alphanumeric type, together
showing the mechanism applies regardless of which character classes
the canonical form mixes (unlike `spaced_digits.py`/`number_words.py`,
which are digit-run-specific, zero-width insertion works identically
between any two characters).

Intentionally omitted: PHONE, IFSC, VEHICLE_REG, UPI, EMAIL — very
likely vulnerable to the identical mechanism (nothing about it is
digit-specific), omitted only to keep this class's own scope small,
not because they are believed safe; PERSON, ORG, ADDRESS — Tier-2/
GLiNER, not regex-based, so this suite does not predict how the model
handles an invisible-character-interrupted name without measuring it
separately, which is out of this class's scope (see
`transliterated_names.py` for this suite's one Tier-2 bypass class).
"""

import random
from typing import Final

from src.core.types import EntityType

from adversarial.cases.carrier import build_slot_case
from adversarial.cases.case_types import AdversarialCase
from benchmarks.generate.entity_values import generate_value

_SEED: Final[int] = 60605

_ENTITY_TYPES: Final[tuple[EntityType, ...]] = ("AADHAAR", "CARD", "PAN")

_ZERO_WIDTH_SPACE: Final[str] = "​"

_PREFIX: Final[str] = "Reference on file: "
_SUFFIX: Final[str] = ". Thank you."


def _zero_width_interspersed(value: str) -> str:
    return _ZERO_WIDTH_SPACE.join(list(value))


def build_cases() -> list[AdversarialCase]:
    rng = random.Random(_SEED)
    cases: list[AdversarialCase] = []
    for entity_type in _ENTITY_TYPES:
        value = generate_value(entity_type, rng)
        cases.append(
            build_slot_case(
                case_id=f"zero_width-{entity_type}-clean",
                bypass_class="zero_width",
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
                case_id=f"zero_width-{entity_type}-adversarial",
                bypass_class="zero_width",
                entity_type=entity_type,
                label="adversarial",
                prefix=_PREFIX,
                embedded_value=_zero_width_interspersed(value),
                suffix=_SUFFIX,
                real_value=value,
                expected_outcome="leaked",
            )
        )
    return cases
