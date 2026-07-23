"""Structural tests for the fixed Phase 7 workload matrix
(`latency/workloads/definitions.py`). These do not spin up the gateway
— that's `latency/runner/`'s job, exercised by the real subprocess
harness, not a fast unit test. What's tested here is that every
workload is well-formed and that the synthetic PII embedded in each one
is actually detectable by the real Tier-1 detectors — the property that
matters most: a workload whose "PII" isn't real-format PII would
silently measure an empty cascade instead of the cost this phase cares
about.
"""

from src.detect.registry import get_tier1_detectors
from latency.workloads.definitions import (
    BASELINE_CLEAN,
    FIELD_WALKER_HEAVY,
    MIXED_DENSE,
    TIER1_ONLY,
    WORKLOADS,
)


def _all_text(value: object) -> str:
    """Flatten every string value anywhere in a JSON-shaped structure —
    good enough for "does this entity value appear somewhere in this
    workload's body" without duplicating field_walker.py's own,
    production-grade traversal."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_all_text(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(_all_text(v) for v in value)
    return ""


def _detected_entity_types(text: str) -> set[str]:
    types: set[str] = set()
    for detector in get_tier1_detectors():
        types.update(span.entity_type for span in detector.detect(text))
    return types


def test_eight_workloads_with_unique_names() -> None:
    assert len(WORKLOADS) == 8
    assert len({w.name for w in WORKLOADS}) == 8


def test_every_workload_request_body_is_openai_shaped() -> None:
    for workload in WORKLOADS:
        assert "model" in workload.request_body
        assert "messages" in workload.request_body
        assert isinstance(workload.request_body["messages"], list)
        assert workload.request_body["messages"]


def test_every_workload_is_streaming() -> None:
    """Every workload in this phase's fixed matrix streams — TTFT has
    no meaning for a non-streaming request, and this phase's own
    primary metric is TTFT (BUILD.md, Phase 7)."""
    for workload in WORKLOADS:
        assert workload.streaming is True


def test_baseline_clean_contains_no_tier1_detectable_entity() -> None:
    text = _all_text(BASELINE_CLEAN.request_body)

    assert _detected_entity_types(text) == set()


def test_tier1_only_contains_aadhaar_pan_and_card() -> None:
    text = _all_text(TIER1_ONLY.request_body)

    detected = _detected_entity_types(text)

    assert "AADHAAR" in detected
    assert "PAN" in detected
    assert "CARD" in detected


def test_mixed_dense_contains_every_structured_entity_type_it_claims() -> None:
    text = _all_text(MIXED_DENSE.request_body)

    detected = _detected_entity_types(text)

    assert {"AADHAAR", "PAN", "CARD", "IFSC", "VEHICLE_REG", "PHONE"} <= detected


def test_no_workload_embeds_email_or_upi() -> None:
    """EMAIL and UPI have no registered surrogate domain today
    (src/pipeline/sanitize.py) -- detecting either raises
    SurrogateDomainError, a 500, before any of the TTFT/rehydration
    behaviour this harness measures ever runs. A workload embedding
    either would silently 500 instead of measuring anything."""
    for workload in WORKLOADS:
        text = _all_text(workload.request_body)
        detected = _detected_entity_types(text)
        assert "EMAIL" not in detected
        assert "UPI" not in detected


def test_field_walker_heavy_plants_pii_outside_messages_content() -> None:
    """The whole point of this workload: PII in the system prompt and
    the tool definition, not only messages[].content -- proven here by
    checking each field independently, not just the flattened whole
    (which mixed_dense-style tests can't distinguish from PII living
    only in the user message)."""
    messages = FIELD_WALKER_HEAVY.request_body["messages"]
    assert isinstance(messages, list)
    system_message = next(m for m in messages if isinstance(m, dict) and m.get("role") == "system")
    assert _detected_entity_types(_all_text(system_message)) == set()  # PERSON/ORG are Tier 2

    tools = FIELD_WALKER_HEAVY.request_body["tools"]
    tool_text = _all_text(tools)
    assert _detected_entity_types(tool_text) == {"IFSC"}


def test_pathological_chunking_reuses_mixed_dense_content_with_a_chunking_directive() -> None:
    from latency.workloads.definitions import PATHOLOGICAL_CHUNKING

    assert PATHOLOGICAL_CHUNKING.request_body["chunking"] == {"n": 40}
    assert (
        PATHOLOGICAL_CHUNKING.request_body["messages"] == MIXED_DENSE.request_body["messages"]
    )
