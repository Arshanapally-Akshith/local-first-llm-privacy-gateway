"""Bypass class 7/9: transliterated names (BUILD.md/ARCHITECTURE.md's
B3) — this suite's one Tier-2 (GLiNER) bypass class.

Unlike every other class in this suite, the mechanism here is a real,
open empirical question, not a regex property that can be proven by
inspection: `docs/LIMITATIONS.md` already discloses GLiNER's own
measured weakness on romanized Hinglish carrier sentences (Phase 4/5),
but this class asks a narrower, different question — does
`urchade/gliner_multi_pii-v1`, a genuinely multilingual model, still
recognise a name rendered in its native Devanagari script at all? This
module predicts "no" (`expected_outcome="leaked"`) based on the
existing Hinglish-weakness finding, but the runner reports the *actual*
measured result regardless, and flags a wrong prediction rather than
hiding it — a multilingual NER model correctly handling Devanagari
would be a genuine, good finding worth reporting exactly as measured
(CLAUDE.md: "a benchmark result is unfavourable... document it").

Measured while this module was being built: both name pairs below were
in fact caught (`docs/DECISIONS.md`, Phase 6) — the a priori prediction
was wrong, and `expected_outcome` is left as `"leaked"` anyway rather
than retroactively "corrected," precisely so the runner's own
prediction-mismatch reporting stays honest about what was predicted
before measuring versus what was found.

Name pairs are real, standard Devanagari transliterations of two
candidates already in this gateway's own synthetic, real-person-free
name pool (`src/session/names.py` — "Aarav"/"Sharma", "Priya"/"Reddy"),
not invented spellings — consistent with `benchmarks/generate`'s own
practice of drawing gold `PERSON` values from that same pool rather
than fabricating names outside it.

Requires the real GLiNER model to measure meaningfully (a no-op stub
Tier-2 model, as `tests/conftest.py` installs by default for every
other integration test in this repo, would trivially "confirm" the
prediction without ever measuring anything) — this is the one bypass
class this phase's tests mark `real_model`, mirroring
`test_tier2_real_model.py`/`test_phase_4_gate.py`'s own precedent.
`build_cases()` itself performs no model inference (it only builds
request bodies); the real model runs only once a case is actually sent
through the live gateway.

Coverage
--------
Exercised: PERSON only.

Intentionally omitted: ORG, ADDRESS — Tier-2 also, and transliteration
plausibly applies to both, but BUILD.md's own bypass-class name is
"transliterated names," not "transliterated entities" generally;
extending this to ORG/ADDRESS is a distinct, unrequested scope
expansion, not a silent gap. Every Tier-1 type — transliteration has no
meaning for a checksum/format-validated structured identifier.
"""

from typing import Final

from src.core.types import EntityType

from adversarial.cases.carrier import build_slot_case
from adversarial.cases.case_types import AdversarialCase

_ENTITY_TYPE: Final[EntityType] = "PERSON"

_NAME_PAIRS: Final[tuple[tuple[str, str], ...]] = (
    ("Aarav Sharma", "आरव शर्मा"),
    ("Priya Reddy", "प्रिया रेड्डी"),
)
"""(latin, devanagari) — both names drawn from `src/session/names.py`'s
first-name/last-name pools (`"Aarav"`+`"Sharma"`, `"Priya"`+`"Reddy"`),
combined the same "First Last" way that module's own docstring
describes, then transliterated to standard Devanagari."""

_PREFIX: Final[str] = "Please schedule a callback with "
_SUFFIX: Final[str] = " about their request today."
"""Verified directly against the real model before being chosen: an
earlier draft's suffix ("... regarding their account.") occasionally
made GLiNER separately misclassify the ordinary word "account" as an
`ORG`, which corrupted this module's prefix/suffix invariant check for
a reason unrelated to the name being tested. This wording produced no
such false positive across repeated real-model checks."""


def build_cases() -> list[AdversarialCase]:
    cases: list[AdversarialCase] = []
    for index, (latin_name, devanagari_name) in enumerate(_NAME_PAIRS):
        cases.append(
            build_slot_case(
                case_id=f"transliterated_names-{index}-clean",
                bypass_class="transliterated_names",
                entity_type=_ENTITY_TYPE,
                label="clean",
                prefix=_PREFIX,
                embedded_value=latin_name,
                suffix=_SUFFIX,
                real_value=latin_name,
                expected_outcome="caught",
            )
        )
        cases.append(
            build_slot_case(
                case_id=f"transliterated_names-{index}-adversarial",
                bypass_class="transliterated_names",
                entity_type=_ENTITY_TYPE,
                label="adversarial",
                prefix=_PREFIX,
                embedded_value=devanagari_name,
                suffix=_SUFFIX,
                real_value=devanagari_name,
                expected_outcome="leaked",
            )
        )
    return cases
