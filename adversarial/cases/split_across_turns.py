"""Bypass class 8/9: split across turns (BUILD.md/ARCHITECTURE.md's
B4) — one of the two classes ARCHITECTURE.md names explicitly as
existing "only at the system level," which is why this suite runs
against the live gateway rather than `cascade.detect()` in isolation
(see `adversarial/__init__.py`).

Mechanism: `src/pipeline/field_walker.py::_walk()` treats each
message's `content` as an independent text leaf and never concatenates
across messages (or any other field) before handing text to the
detection cascade — by design, not oversight (`sanitize()`'s own
docstring: "field_walker.rebuild() is called exactly once, after every
region has been walked"; each region is scanned on its own). A real
multi-turn client resends the entire conversation history with every
request (the OpenAI chat-completion wire format has no other way to
carry context), so an entity whose digits are split across two
messages — one turn giving the first half, a later turn giving the
rest — is never present as one contiguous run in *either* message, even
though both halves arrive in the very same request body. Verified
empirically before this module was written: neither a 7-digit nor a
5-digit fragment of a 12-digit Aadhaar matches any registered Tier-1
candidate pattern in isolation.

This mechanism needs its own verifier
(`adversarial.cases.verify.fragment_reconstruction`), not
`build_slot_case()`/`slot_replacement()` — there is no single slot to
check prefix/suffix invariance around, because the two halves live in
two different fields entirely. See that function's own docstring for
what "caught" can honestly mean when there is no single detectable span
to substitute in the first place.

Coverage
--------
Exercised: AADHAAR, PHONE — both pure-digit-run Tier-1 types, split at a
point confirmed (per this module's own fragment-safety check, run at
generation time) not to accidentally form a *different* detectable
entity in either half.

Intentionally omitted: PAN (mixed letter/digit — splitting it cleanly
in two would need its own, separately-reasoned split point rather than
reusing this module's simple midpoint-of-digits approach); CARD, IFSC,
VEHICLE_REG, UPI, EMAIL — likely vulnerable to the identical
independent-field mechanism, omitted only to keep this class's scope
small; PERSON, ORG, ADDRESS — splitting a *name* across turns is a
qualitatively different, session-map-and-coreference question (would
the model even resolve "the person I mentioned earlier" without a name
repeated in full?) that this class does not attempt to answer.
"""

import random
from typing import Final

from src.core.types import EntityType
from src.detect import precedence
from src.detect.registry import get_tier1_detectors
from src.pipeline.field_walker import JSONValue

from adversarial.cases.carrier import build_slot_case
from adversarial.cases.case_types import AdversarialCase
from adversarial.cases.verify import fragment_reconstruction
from benchmarks.generate.entity_values import generate_value

_SEED: Final[int] = 60608

_ENTITY_TYPES: Final[tuple[EntityType, ...]] = ("AADHAAR", "PHONE")
_MODEL: Final[str] = "gpt-4"

_TURN_1_PREFIX: Final[str] = "The first part of my reference number is "
_TURN_2_PREFIX: Final[str] = "The rest of it is "


def _fragment_is_undetectable_alone(fragment: str) -> bool:
    """True iff no registered Tier-1 detector, run on `fragment` alone,
    resolves any span at all — the property this class's entire premise
    depends on, checked directly against the real detectors (CLAUDE.md:
    "measure, don't assume") rather than assumed from fragment length."""
    spans_per_detector = [detector.detect(fragment) for detector in get_tier1_detectors()]
    return precedence.resolve(spans_per_detector) == []


def _split_point(entity_type: EntityType) -> int:
    """Where to cut the canonical value: roughly in half, landing on a
    digit boundary — AADHAAR (12 digits) splits 7/5, PHONE (10 digits,
    optionally prefixed) splits so neither half is itself 10-12
    contiguous digits."""
    return {"AADHAAR": 7, "PHONE": 5}[entity_type]


def _split_turns_body(turn_1_text: str, turn_2_text: str) -> JSONValue:
    """A real multi-turn client resends the whole transcript on every
    call; this is that shape collapsed into the one request the second
    turn would actually send — an assistant turn sits between the two
    user turns for realism, but carries no PII and plays no role in the
    mechanism."""
    return {
        "model": _MODEL,
        "messages": [
            {"role": "user", "content": turn_1_text},
            {"role": "assistant", "content": "Thanks, I've noted the first part."},
            {"role": "user", "content": turn_2_text},
        ],
        "stream": False,
    }


def build_cases() -> list[AdversarialCase]:
    rng = random.Random(_SEED)
    cases: list[AdversarialCase] = []
    for entity_type in _ENTITY_TYPES:
        value = generate_value(entity_type, rng)
        cut = _split_point(entity_type)
        fragment_1, fragment_2 = value[:cut], value[cut:]
        assert _fragment_is_undetectable_alone(fragment_1), (
            f"fragment_1={fragment_1!r} for {entity_type} unexpectedly matched a Tier-1 "
            "detector alone - this class's premise (neither half is independently "
            "detectable) does not hold for this split point"
        )
        assert _fragment_is_undetectable_alone(fragment_2), (
            f"fragment_2={fragment_2!r} for {entity_type} unexpectedly matched a Tier-1 "
            "detector alone - this class's premise does not hold for this split point"
        )

        cases.append(
            build_slot_case(
                case_id=f"split_across_turns-{entity_type}-clean",
                bypass_class="split_across_turns",
                entity_type=entity_type,
                label="clean",
                prefix="My reference number is ",
                embedded_value=value,
                suffix=", please confirm.",
                real_value=value,
                expected_outcome="caught",
            )
        )

        turn_1_text = _TURN_1_PREFIX + fragment_1
        turn_2_text = _TURN_2_PREFIX + fragment_2
        cases.append(
            AdversarialCase(
                case_id=f"split_across_turns-{entity_type}-adversarial",
                bypass_class="split_across_turns",
                entity_type=entity_type,
                label="adversarial",
                request_body=_split_turns_body(turn_1_text, turn_2_text),
                expected_outcome="leaked",
                verify=fragment_reconstruction(
                    [
                        (("messages", 0, "content"), fragment_1),
                        (("messages", 2, "content"), fragment_2),
                    ]
                ),
            )
        )
    return cases
