"""The fixed, deterministic 8-workload matrix (Phase 7 design, "What
workloads should be benchmarked").

Each workload isolates exactly one cost axis; none combines two (PII
density x turn depth x chunking x field shape) — the same ablation
discipline `benchmarks/arms/` applies to accuracy, applied here to
latency. Every entity value is generated once, at import time, from a
fixed seed via `benchmarks.generate.entity_values.generate_value` — the
same synthetic-entity generator the Phase 5 benchmark dataset itself
uses, not a second, independently-drifting one (CLAUDE.md: "no
duplicated logic"). Every request here is fully synthetic, matching
CLAUDE.md's "synthetic PII only in this repo" rule.
"""

import random
from typing import Final

from benchmarks.generate.entity_values import generate_value

from src.pipeline.field_walker import JSONValue

from latency.workloads.workload_types import LatencyWorkload

_SEED: Final[int] = 0
"""Fixed, not system entropy — mirrors `rehydration_fidelity/runner/run.py`'s
own `_ALLOCATION_SEED` and `benchmarks/generate/seed.py`'s identical
reasoning: this harness's own workload content must be reproducible run
to run until the code that generates it actually changes. The value
itself carries no meaning beyond determinism."""

_rng: Final[random.Random] = random.Random(_SEED)
_MODEL: Final[str] = "gpt-4"

_AADHAAR: Final[str] = generate_value("AADHAAR", _rng)
_PAN: Final[str] = generate_value("PAN", _rng)
_CARD: Final[str] = generate_value("CARD", _rng)
_IFSC: Final[str] = generate_value("IFSC", _rng)
_VEHICLE_REG: Final[str] = generate_value("VEHICLE_REG", _rng)
_PERSON: Final[str] = generate_value("PERSON", _rng)
_ORG: Final[str] = generate_value("ORG", _rng)
_ADDRESS: Final[str] = generate_value("ADDRESS", _rng)
_PHONE: Final[str] = generate_value("PHONE", _rng)
# EMAIL and UPI are deliberately never used below: neither has a
# registered surrogate domain today (src/pipeline/sanitize.py's own
# docstring; ARCHITECTURE.md's FF1 Engine failure modes), so detecting
# either raises SurrogateDomainError -> 500 before any of the
# TTFT/rehydration behaviour this harness measures ever runs. A known,
# documented repo gap (docs/LIMITATIONS.md), not something for a
# latency workload to route around.


def _user_message(content: str) -> dict[str, JSONValue]:
    return {
        "model": _MODEL,
        "messages": [{"role": "user", "content": content}],
        "stream": True,
    }


BASELINE_CLEAN: Final[LatencyWorkload] = LatencyWorkload(
    name="baseline_clean",
    description=(
        "Zero-PII cost floor: a single short message with no detectable "
        "entity. Tier 1 and Tier 2 both still run and both find nothing "
        "-- the honest 'real traffic is mostly PII-free' case "
        "(ARCHITECTURE.md, 'The cascade')."
    ),
    request_body=_user_message("What time zone is Bengaluru in?"),
)

TIER1_ONLY: Final[LatencyWorkload] = LatencyWorkload(
    name="tier1_only",
    description=(
        "Deterministic-path cost: structured entities only (Aadhaar, "
        "PAN, card), no names/orgs/addresses."
    ),
    request_body=_user_message(
        f"My Aadhaar is {_AADHAAR}, PAN is {_PAN}, and card number is {_CARD}."
    ),
)

TIER2_ONLY: Final[LatencyWorkload] = LatencyWorkload(
    name="tier2_only",
    description=(
        "Model-inference cost: unstructured entities only (person, org, "
        "address), no structured entities."
    ),
    request_body=_user_message(f"{_PERSON} from {_ORG} lives at {_ADDRESS}."),
)

MIXED_DENSE: Final[LatencyWorkload] = LatencyWorkload(
    name="mixed_dense",
    description=(
        "Combined-cascade cost: one of every entity type with a "
        "registered surrogate domain, across both tiers (EMAIL/UPI "
        "excluded -- see the module-level note above)."
    ),
    request_body=_user_message(
        f"{_PERSON} from {_ORG} at {_ADDRESS}, Aadhaar {_AADHAAR}, PAN {_PAN}, "
        f"card {_CARD}, IFSC {_IFSC}, vehicle {_VEHICLE_REG}, phone {_PHONE}."
    ),
)

MULTITURN_5: Final[LatencyWorkload] = LatencyWorkload(
    name="multiturn_5",
    description=(
        "Session-map growth over an extended, 5-turn message history "
        "(5 distinct real-valued entities needing allocation/FF1 within "
        "one sanitize() call). This is NOT a live ingress-surrogate "
        "scenario: constructing one honestly would require already "
        "knowing this exact session's own FF1/name-allocation output, "
        "which a static, pre-generated workload cannot predict ahead of "
        "a real run against a real FPE_KEY. Ingress-recognition "
        "correctness itself is already covered by Phase 3's own "
        "dedicated tests; what this workload isolates for latency "
        "purposes is the cost of a longer accumulated session, not that "
        "one specific branch."
    ),
    request_body={
        "model": _MODEL,
        "stream": True,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": f"My name is {_PERSON}, from {_ORG}."},
            {"role": "assistant", "content": f"Noted, {_PERSON}."},
            {"role": "user", "content": f"My Aadhaar is {_AADHAAR}."},
            {"role": "assistant", "content": f"Got it, {_AADHAAR} on file."},
            {"role": "user", "content": f"And my PAN is {_PAN}."},
            {"role": "assistant", "content": f"Noted, {_PAN}."},
            {
                "role": "user",
                "content": f"One more thing, {_PERSON} -- my address is {_ADDRESS}.",
            },
            {"role": "assistant", "content": "Understood."},
            {"role": "user", "content": "Can you summarize what you have on file for me?"},
        ],
    },
)

FIELD_WALKER_HEAVY: Final[LatencyWorkload] = LatencyWorkload(
    name="field_walker_heavy",
    description=(
        "Field-walking cost independent of PII density: PII planted in "
        "the system prompt, a tool definition, and a tool-result "
        "message -- not just messages[].content (ARCHITECTURE.md, Body "
        "Field Walker: 'the field you forget is the leak')."
    ),
    request_body={
        "model": _MODEL,
        "stream": True,
        "messages": [
            {"role": "system", "content": f"You are assisting {_PERSON} from {_ORG}."},
            {"role": "user", "content": "Look up the account and confirm the phone number."},
            {"role": "tool", "content": f"Account holder phone on file: {_PHONE}."},
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "lookup_account",
                    "description": f"Looks up the account for {_PERSON} at {_ORG}.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ifsc": {"type": "string", "description": f"e.g. {_IFSC}"}
                        },
                    },
                },
            }
        ],
    },
)

PATHOLOGICAL_CHUNKING: Final[LatencyWorkload] = LatencyWorkload(
    name="pathological_chunking",
    description=(
        "Window/rehydration cost under stress: mixed_dense's own request "
        "body, plus the mock's `chunking.n` directive forcing every "
        "surrogate in the echoed response across 40 chunks "
        "(src/mock_upstream/chunking.py) -- isolates rehydration-under- "
        "fragmentation cost from normal streaming cost."
    ),
    request_body={**MIXED_DENSE.request_body, "chunking": {"n": 40}},
)

LONG_RESPONSE: Final[LatencyWorkload] = LatencyWorkload(
    name="long_response",
    description=(
        "Window accumulation over a long stream: 20 short paragraphs, "
        "each naming a distinct person and org, normal (non- "
        "pathological) chunking -- isolates whether window overhead "
        "compounds over stream length rather than per-surrogate."
    ),
    request_body=_user_message(
        " ".join(
            f"Paragraph about {generate_value('PERSON', _rng)} from "
            f"{generate_value('ORG', _rng)}."
            for _ in range(20)
        )
    ),
)

WORKLOADS: Final[tuple[LatencyWorkload, ...]] = (
    BASELINE_CLEAN,
    TIER1_ONLY,
    TIER2_ONLY,
    MIXED_DENSE,
    MULTITURN_5,
    FIELD_WALKER_HEAVY,
    PATHOLOGICAL_CHUNKING,
    LONG_RESPONSE,
)
"""Every workload the harness runs, in a fixed order — deterministic
and diffable, the same discipline
`adversarial/cases/discovery.py::discover_cases()`'s own sorted
ordering applies to that suite."""
