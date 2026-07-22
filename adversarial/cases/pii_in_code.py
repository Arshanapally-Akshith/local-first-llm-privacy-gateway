"""Bypass class 3/9: PII inside code (BUILD.md/ARCHITECTURE.md's B6).

Mechanism, verified empirically before this module was written:
`AadhaarDetector` and `PanDetector` anchor their candidate patterns with
`\\b` (`src/detect/tier1/aadhaar.py`: `\\b\\d{12}\\b`; `pan.py`:
`\\b[A-Z]{5}\\d{4}[A-Z]\\b`). Python's `re` module treats `_` as a word
character for `\\b` purposes (`\\w` includes `[A-Za-z0-9_]`), so an
entity glued directly to an underscore on either side — exactly how a
value gets embedded in a `snake_case` code identifier
(`aadhaar_999912345676_verified`) — has no word-boundary transition for
`\\b` to anchor on, and the whole pattern fails to match starting
there. Confirmed directly:

    >>> import re
    >>> re.findall(r"\\b\\d{12}\\b", "aadhaar_999912345676_verified")
    []

`PhoneDetector`, `EmailDetector`, and `UpiDetector` do **not** share
this weakness — they anchor with an explicit `(?<![A-Za-z0-9]...)`
negative-lookaround character class that does not include `_`, so an
underscore-adjacent phone number (`contact_9876543210_now`) still
matches. This asymmetry is real, not a simplification on this module's
part, and is exactly why those three types are omitted below rather
than included and silently failing to demonstrate anything.

Coverage
--------
Exercised: AADHAAR, PAN — the two Tier-1 types whose candidate pattern
is `\\b`-anchored, confirmed to actually lose the boundary under this
mechanism.

Intentionally omitted: CARD, IFSC, VEHICLE_REG — also `\\b`-anchored
and very likely vulnerable to the identical mechanism, but not included
here to keep this class's own scope small and legible (BUILD.md's
"each bypass class is a runnable case," not "every case a mechanism
could possibly apply to"); a real gap for a future extension of this
class, not a claim that these three are safe. PHONE, EMAIL, UPI — not
vulnerable to *this* mechanism at all, per the boundary-style difference
above (a genuine negative finding, stated rather than omitted silently).
PERSON, ORG, ADDRESS — Tier-2/GLiNER, not regex-based, so `\\b` has no
bearing on them; see `transliterated_names.py` for this suite's one
Tier-2 bypass class.
"""

import random
from typing import Final

from src.core.types import EntityType

from adversarial.cases.carrier import build_slot_case
from adversarial.cases.case_types import AdversarialCase
from benchmarks.generate.entity_values import generate_value

_SEED: Final[int] = 60603

_ENTITY_TYPES: Final[tuple[EntityType, ...]] = ("AADHAAR", "PAN")

_PREFIX: Final[str] = "customer_record = {'aadhaar_"
_SUFFIX: Final[str] = "_verified': True}\n# TODO: move to config"


def build_cases() -> list[AdversarialCase]:
    rng = random.Random(_SEED)
    cases: list[AdversarialCase] = []
    for entity_type in _ENTITY_TYPES:
        value = generate_value(entity_type, rng)
        clean_prefix = "The verified identifier is "
        clean_suffix = " — please confirm."
        cases.append(
            build_slot_case(
                case_id=f"pii_in_code-{entity_type}-clean",
                bypass_class="pii_in_code",
                entity_type=entity_type,
                label="clean",
                prefix=clean_prefix,
                embedded_value=value,
                suffix=clean_suffix,
                real_value=value,
                expected_outcome="caught",
            )
        )
        cases.append(
            build_slot_case(
                case_id=f"pii_in_code-{entity_type}-adversarial",
                bypass_class="pii_in_code",
                entity_type=entity_type,
                label="adversarial",
                prefix=_PREFIX,
                embedded_value=value,
                suffix=_SUFFIX,
                real_value=value,
                expected_outcome="leaked",
            )
        )
    return cases
