"""Bypass class 4/9: base64 (BUILD.md/ARCHITECTURE.md's B5).

Mechanism: the frozen architecture (CLAUDE.md, ARCHITECTURE.md) is
Tier 1 (checksum/regex over the literal text) plus Tier 2 (GLiNER over
the literal text) — there is no content-decoding stage of any kind
(base64, hex, URL-encoding, ...) anywhere in the cascade, by design,
not by oversight (`field_walker.py`'s own docstring: "blanket
content-sniffing... would risk re-serializing a user's literal
JSON-looking message text with different formatting on rebuild, for no
privacy benefit"). A canonical entity value, base64-encoded before
being placed in a message, therefore never appears in the literal text
any detector scans, and the encoded blob — trivially reversible by
anyone downstream who recognises it as base64 — crosses to upstream
completely unchanged.

Coverage
--------
Exercised: AADHAAR, CARD — representative Tier-1 structured types;
base64 has no dependency on the entity's own shape (it operates on the
encoded bytes, not the plaintext structure), so the mechanism is
identical regardless of which entity type is chosen. Two types are
enough to demonstrate this without implying the other seven would
behave any differently — they would, for the identical reason.

Intentionally omitted: every other entity type — the "no decoding
stage" mechanism applies uniformly to all eleven `EntityType`s;
covering all eleven here would not surface any new information, only
repeat the same finding eleven times.
"""

import base64
import random
from typing import Final

from src.core.types import EntityType

from adversarial.cases.carrier import build_slot_case
from adversarial.cases.case_types import AdversarialCase
from benchmarks.generate.entity_values import generate_value

_SEED: Final[int] = 60604

_ENTITY_TYPES: Final[tuple[EntityType, ...]] = ("AADHAAR", "CARD")

_PREFIX: Final[str] = "Here is the encoded record for your system: "
_SUFFIX: Final[str] = " (base64, decode client-side)."


def _b64(value: str) -> str:
    return base64.b64encode(value.encode("ascii")).decode("ascii")


def build_cases() -> list[AdversarialCase]:
    rng = random.Random(_SEED)
    cases: list[AdversarialCase] = []
    for entity_type in _ENTITY_TYPES:
        value = generate_value(entity_type, rng)
        cases.append(
            build_slot_case(
                case_id=f"base64_encoding-{entity_type}-clean",
                bypass_class="base64_encoding",
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
                case_id=f"base64_encoding-{entity_type}-adversarial",
                bypass_class="base64_encoding",
                entity_type=entity_type,
                label="adversarial",
                prefix=_PREFIX,
                embedded_value=_b64(value),
                suffix=_SUFFIX,
                real_value=value,
                expected_outcome="leaked",
            )
        )
    return cases
