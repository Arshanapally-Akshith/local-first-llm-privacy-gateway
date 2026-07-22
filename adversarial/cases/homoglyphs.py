"""Bypass class 6/9: Unicode homoglyphs (BUILD.md/ARCHITECTURE.md's
B8).

Mechanism, verified empirically before this module was written, and
non-obvious enough to spell out exactly: Python's `re` module treats
`\\b` as Unicode-aware by default for `str` patterns — a Cyrillic
letter counts as a `\\w` character, the same as a Latin one. Swapping
the PAN's or IFSC's first Latin letter for a Cyrillic homoglyph (real
UTS #39 confusables — see `_HOMOGLYPH_FOR_FIRST_LETTER`'s own docstring
for why the exact replaced letter doesn't need to visually match) does
*not* create a word-boundary break the way `pii_in_code.py`'s underscore
trick does — quite the opposite: because both the homoglyph and the
following ASCII letter are `\\w` characters, `\\b` never fires *between*
them either, which means the pattern can never anchor its opening `\\b`
at the position immediately after the homoglyph. The character class
`[A-Z]` also flatly rejects the Cyrillic character itself. Both effects
combine to produce a clean, total miss — confirmed directly:

    >>> import re
    >>> re.findall(r"\\b[A-Z]{5}\\d{4}[A-Z]\\b", "pan is " + "\\u0410" + "AAPL1234C")
    []

This is a different failure shape from `email.py`'s pattern, which is
worth naming precisely rather than glossing over: `EmailDetector`
anchors with an explicit character-class lookaround
(`(?<![A-Za-z0-9._%+-])...`), not `\\b`, so a homoglyph there does not
merge two boundary-adjacent tokens the way it does for a `\\b`-anchored
pattern — instead the regex engine simply resumes matching from the
next in-class character, producing a *partial, wrong-span* match
(confirmed: `"аravikumar@example.com"` with a Cyrillic `а` matches
`"ravikumar@example.com"` minus its first letter) rather than a clean
miss. A wrong-span partial match is arguably a *more* concerning
failure mode than a clean miss (it could substitute the wrong
substring), but it does not fit this suite's binary caught/leaked
model, which is why EMAIL is omitted below rather than included with a
result this suite cannot characterize honestly.

Coverage
--------
Exercised: PAN, IFSC — both `\\b`-anchored, both confirmed to produce a
clean total miss under this exact mechanism.

Intentionally omitted: AADHAAR, CARD (pure-digit canonical forms —
Latin/Cyrillic homoglyphs are a letter-substitution attack and have no
meaningful analogue over a digit-only alphabet); VEHICLE_REG (also
`\\b`-anchored and structurally similar to PAN/IFSC, very likely
vulnerable to the identical mechanism — omitted to keep this class's
scope small, not because it is believed safe); PHONE, UPI (digit-heavy
or lookaround-anchored, not meaningfully letter-substitutable in the
same way); EMAIL — the partial-match failure mode above, a real,
disclosed gap in this suite's own model, not a silent omission; PERSON,
ORG, ADDRESS — Tier-2/GLiNER homoglyph robustness is a genuinely
separate, model-dependent question this suite does not attempt to
answer without measuring it directly (out of scope here — see
`transliterated_names.py` for this suite's one Tier-2 bypass class).
"""

import random
from typing import Final

from src.core.types import EntityType

from adversarial.cases.carrier import build_slot_case
from adversarial.cases.case_types import AdversarialCase
from benchmarks.generate.entity_values import generate_value

_SEED: Final[int] = 60606

_ENTITY_TYPES: Final[tuple[EntityType, ...]] = ("PAN", "IFSC")

_HOMOGLYPH_FOR_FIRST_LETTER: Final[dict[EntityType, str]] = {
    "PAN": "А",  # Cyrillic CAPITAL A (U+0410) — a real UTS #39 confusable for Latin 'A'.
    "IFSC": "Н",  # Cyrillic CAPITAL EN (U+041D) — a real UTS #39 confusable for Latin 'H'.
}
"""One documented, real Unicode confusable per entity type (Unicode
Technical Standard #39's confusables data), always substituted for
whichever first letter `generate_value()` actually produced — both
generators pick a uniformly random uppercase Latin letter there
(`entity_values.py::_generate_pan`/`_generate_ifsc`), so the swapped-in
character is not always visually identical to the specific letter it
replaces. This does not weaken the mechanism: the regex rejects *any*
non-ASCII character in an `[A-Z]` class outright, regardless of which
Latin letter it happens to resemble, so visual similarity to the exact
replaced letter is a realism nicety for this module's carrier text, not
a mechanical requirement — stated here so a future reader doesn't
assume the substitution is more targeted than it is."""

_PREFIX: Final[str] = "Confirmed identifier: "
_SUFFIX: Final[str] = " (verified twice)."


def _with_homoglyph_first_letter(value: str, entity_type: EntityType) -> str:
    return _HOMOGLYPH_FOR_FIRST_LETTER[entity_type] + value[1:]


def build_cases() -> list[AdversarialCase]:
    rng = random.Random(_SEED)
    cases: list[AdversarialCase] = []
    for entity_type in _ENTITY_TYPES:
        value = generate_value(entity_type, rng)
        cases.append(
            build_slot_case(
                case_id=f"homoglyphs-{entity_type}-clean",
                bypass_class="homoglyphs",
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
                case_id=f"homoglyphs-{entity_type}-adversarial",
                bypass_class="homoglyphs",
                entity_type=entity_type,
                label="adversarial",
                prefix=_PREFIX,
                embedded_value=_with_homoglyph_first_letter(value, entity_type),
                suffix=_SUFFIX,
                real_value=value,
                expected_outcome="leaked",
            )
        )
    return cases
