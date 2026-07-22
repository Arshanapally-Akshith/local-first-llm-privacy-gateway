"""Bypass class 9/9: PII inside JSON (BUILD.md/ARCHITECTURE.md's B7),
implemented as PII-placed-as-a-JSON-*key* — the second of the two
classes ARCHITECTURE.md names as existing "only at the system level"
(see `split_across_turns.py`'s module docstring for the first).

Mechanism: `src/pipeline/field_walker.py::_walk()`'s traversal is

    for key, child in value.items():
        yield from _walk(child, (*path, key))

which recurses into every dict *value* and never visits, or emits a
`TextRegion` for, a dict *key* itself. A tool call's `arguments` field
(the one place this codebase already transparently JSON-parses a
string field, per `field_walker.py`'s own module docstring) normally
carries an entity as a value (`{"aadhaar": "999912345676"}` — already
proven detectable, e.g. `tests/integration/test_sanitize_integration.py`).
Placing the identical value as a *key* instead
(`{"999912345676": "primary_account_holder"}`) makes it structurally
invisible to the walker: nothing in the sanitize pipeline ever looks at
it, so it crosses to upstream completely unmodified.

Coverage
--------
Exercised: AADHAAR, PHONE — the same two Tier-1 types
`split_across_turns.py` covers, for comparability across this suite's
two "system-level-only" classes; the JSON-key mechanism itself has no
dependency on which entity type is used (it operates on `field_walker`'s
traversal order, not on any entity's own shape).

Intentionally omitted: every other entity type — the mechanism applies
uniformly to all eleven `EntityType`s (a dict key is a dict key
regardless of what it structurally looks like); covering more of them
would not surface new information, only repeat the same finding.
"""

import json
import random
from typing import Final

from src.core.types import EntityType
from src.pipeline.field_walker import JSONValue

from adversarial.cases.carrier import build_slot_case
from adversarial.cases.case_types import AdversarialCase
from adversarial.cases.verify import key_presence
from benchmarks.generate.entity_values import generate_value

_SEED: Final[int] = 60609

_ENTITY_TYPES: Final[tuple[EntityType, ...]] = ("AADHAAR", "PHONE")
_MODEL: Final[str] = "gpt-4"
_ARGUMENTS_FIELD_PATH: Final[tuple[str | int, ...]] = (
    "messages",
    0,
    "tool_calls",
    0,
    "function",
    "arguments",
)


def _tool_call_body(value: str) -> JSONValue:
    """A single assistant turn making one tool call whose `arguments`
    JSON-string field uses `value` as a key rather than a value —
    `field_walker.py`'s own transparent-JSON-string-unwrap rule (`path[-1]
    == "arguments"`) is what makes this field's *values* detectable at
    all; this case exploits the fact that the same rule never looks at
    keys."""
    arguments = json.dumps({value: "primary_account_holder"})
    return {
        "model": _MODEL,
        "messages": [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "log_account_note", "arguments": arguments},
                    }
                ],
            }
        ],
        "stream": False,
    }


def build_cases() -> list[AdversarialCase]:
    rng = random.Random(_SEED)
    cases: list[AdversarialCase] = []
    for entity_type in _ENTITY_TYPES:
        value = generate_value(entity_type, rng)
        cases.append(
            build_slot_case(
                case_id=f"pii_in_json_key-{entity_type}-clean",
                bypass_class="pii_in_json_key",
                entity_type=entity_type,
                label="clean",
                prefix="For reference, the identifier is ",
                embedded_value=value,
                suffix=" on the account.",
                real_value=value,
                expected_outcome="caught",
            )
        )
        cases.append(
            AdversarialCase(
                case_id=f"pii_in_json_key-{entity_type}-adversarial",
                bypass_class="pii_in_json_key",
                entity_type=entity_type,
                label="adversarial",
                request_body=_tool_call_body(value),
                expected_outcome="leaked",
                verify=key_presence(container_field_path=_ARGUMENTS_FIELD_PATH, key=value),
            )
        )
    return cases
