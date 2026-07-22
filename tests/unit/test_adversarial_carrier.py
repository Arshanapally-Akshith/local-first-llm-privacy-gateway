"""`adversarial.cases.carrier.build_slot_case` — the shared builder 7
of this suite's 9 bypass-class modules use."""

import json

from adversarial.cases.carrier import build_slot_case


def test_build_slot_case_embeds_text_between_prefix_and_suffix() -> None:
    case = build_slot_case(
        case_id="test-clean",
        bypass_class="test_class",
        entity_type="AADHAAR",
        label="clean",
        prefix="ref: ",
        embedded_value="999912345676",
        suffix=" end",
        real_value="999912345676",
        expected_outcome="caught",
    )
    body = case.request_body
    assert isinstance(body, dict)
    messages = body["messages"]
    assert isinstance(messages, list)
    first_message = messages[0]
    assert isinstance(first_message, dict)
    assert first_message["content"] == "ref: 999912345676 end"
    assert first_message["role"] == "user"
    assert body["stream"] is False


def test_build_slot_case_preserves_every_field_verbatim() -> None:
    case = build_slot_case(
        case_id="case-1",
        bypass_class="my_class",
        entity_type="PAN",
        label="adversarial",
        prefix="p",
        embedded_value="v",
        suffix="s",
        real_value="real",
        expected_outcome="leaked",
    )
    assert case.case_id == "case-1"
    assert case.bypass_class == "my_class"
    assert case.entity_type == "PAN"
    assert case.label == "adversarial"
    assert case.expected_outcome == "leaked"


def test_build_slot_case_verifier_uses_sent_value_not_real_value_for_replacement_check() -> None:
    """Regression test for the bug caught before this suite's first
    real run: `replacement_present` must compare the surviving field
    text against what was actually *sent* (`embedded_value`), not the
    true plaintext (`real_value`) — otherwise an untouched, obfuscated
    value (which differs from `real_value` by construction) would be
    wrongly read as "replaced" just because it doesn't equal
    `real_value`."""
    case = build_slot_case(
        case_id="regression-case",
        bypass_class="test_class",
        entity_type="AADHAAR",
        label="adversarial",
        prefix="ref: ",
        embedded_value="9999 1234 5676",
        suffix=" end",
        real_value="999912345676",
        expected_outcome="leaked",
    )
    unchanged_capture = json.dumps(
        {"messages": [{"content": "ref: 9999 1234 5676 end"}]}
    ).encode("utf-8")
    outcome = case.verify(unchanged_capture)
    assert outcome.replacement_present is False
    assert outcome.caught is False
