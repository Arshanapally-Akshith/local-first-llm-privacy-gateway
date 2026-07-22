"""`adversarial.cases.verify` — the three shared verifier builders,
tested directly against hand-built captured-bytes fixtures rather than
a live gateway call, so these tests stay fast and isolate exactly what
each verifier computes from what it is given.
"""

import json

from adversarial.cases.verify import fragment_reconstruction, key_presence, slot_replacement


def _body_bytes(**body: object) -> bytes:
    return json.dumps(body).encode("utf-8")


class TestSlotReplacement:
    def test_unchanged_field_is_not_caught(self) -> None:
        """The gateway did nothing: the field still contains exactly
        what was sent (prefix + the literal sent value + suffix) — this
        must never read as `caught`, regardless of whether `sent_value`
        happens to differ textually from `real_value` (the obfuscated-
        but-untouched case this suite's whole premise depends on)."""
        verify = slot_replacement(
            field_path=("messages", 0, "content"),
            prefix="ref: ",
            suffix=" end",
            real_value="123456789012",
            sent_value="1234 5678 9012",
        )
        body = _body_bytes(messages=[{"content": "ref: 1234 5678 9012 end"}])
        outcome = verify(body)
        assert outcome.structurally_valid_json is True
        assert outcome.replacement_present is False
        assert outcome.caught is False

    def test_substituted_field_is_caught_regardless_of_surrogate_value(self) -> None:
        """A generic future-proof check: any different, non-empty
        middle value between the known prefix/suffix reads as a real
        replacement, without hardcoding what a surrogate looks like."""
        verify = slot_replacement(
            field_path=("messages", 0, "content"),
            prefix="ref: ",
            suffix=" end",
            real_value="123456789012",
            sent_value="123456789012",
        )
        body = _body_bytes(messages=[{"content": "ref: 000000000099 end"}])
        outcome = verify(body)
        assert outcome.original_absent is True
        assert outcome.replacement_present is True
        assert outcome.caught is True

    def test_original_value_present_elsewhere_in_body_is_not_original_absent(self) -> None:
        verify = slot_replacement(
            field_path=("messages", 0, "content"),
            prefix="ref: ",
            suffix=" end",
            real_value="123456789012",
            sent_value="123456789012",
        )
        body = _body_bytes(
            messages=[
                {"content": "ref: 000000000099 end"},
                {"content": "leaked elsewhere: 123456789012"},
            ]
        )
        outcome = verify(body)
        assert outcome.original_absent is False
        assert outcome.caught is False

    def test_changed_surrounding_carrier_text_is_not_replacement_present(self) -> None:
        """A blanket redaction or truncation that also eats the
        surrounding carrier text must not be mistaken for a targeted
        substitution."""
        verify = slot_replacement(
            field_path=("messages", 0, "content"),
            prefix="ref: ",
            suffix=" end",
            real_value="123456789012",
            sent_value="123456789012",
        )
        body = _body_bytes(messages=[{"content": "[REDACTED]"}])
        outcome = verify(body)
        assert outcome.replacement_present is False
        assert outcome.caught is False

    def test_invalid_json_is_not_structurally_valid(self) -> None:
        verify = slot_replacement(
            field_path=("messages", 0, "content"),
            prefix="ref: ",
            suffix=" end",
            real_value="123456789012",
            sent_value="123456789012",
        )
        outcome = verify(b"{not valid json")
        assert outcome.structurally_valid_json is False
        assert outcome.caught is False

    def test_missing_field_path_is_not_caught(self) -> None:
        verify = slot_replacement(
            field_path=("messages", 0, "content"),
            prefix="ref: ",
            suffix=" end",
            real_value="123456789012",
            sent_value="123456789012",
        )
        body = _body_bytes(messages=[])
        outcome = verify(body)
        assert outcome.structurally_valid_json is True
        assert outcome.replacement_present is False
        assert outcome.caught is False


class TestFragmentReconstruction:
    def test_both_fragments_intact_is_not_caught(self) -> None:
        """The expected shape for a genuine split-across-turns leak:
        neither half was ever independently detectable, so both survive
        unchanged and the full value is reconstructable from the
        transcript."""
        verify = fragment_reconstruction(
            [
                (("messages", 0, "content"), "9999123"),
                (("messages", 2, "content"), "45676"),
            ]
        )
        body = _body_bytes(
            messages=[
                {"content": "first part: 9999123"},
                {"content": "noted"},
                {"content": "rest: 45676"},
            ]
        )
        outcome = verify(body)
        assert outcome.original_absent is False
        assert outcome.replacement_present is False
        assert outcome.caught is False

    def test_a_changed_fragment_is_caught(self) -> None:
        verify = fragment_reconstruction(
            [
                (("messages", 0, "content"), "9999123"),
                (("messages", 2, "content"), "45676"),
            ]
        )
        body = _body_bytes(
            messages=[
                {"content": "first part: 0000000"},
                {"content": "noted"},
                {"content": "rest: 45676"},
            ]
        )
        outcome = verify(body)
        assert outcome.original_absent is True
        assert outcome.replacement_present is True
        assert outcome.caught is True


class TestKeyPresence:
    def test_key_present_unmodified_is_not_caught(self) -> None:
        verify = key_presence(
            container_field_path=("messages", 0, "tool_calls", 0, "function", "arguments"),
            key="999912345676",
        )
        arguments = json.dumps({"999912345676": "primary_account_holder"})
        body = _body_bytes(
            messages=[
                {"tool_calls": [{"function": {"arguments": arguments}}]},
            ]
        )
        outcome = verify(body)
        assert outcome.original_absent is False
        assert outcome.caught is False

    def test_key_absent_is_caught(self) -> None:
        verify = key_presence(
            container_field_path=("messages", 0, "tool_calls", 0, "function", "arguments"),
            key="999912345676",
        )
        arguments = json.dumps({"note": "primary_account_holder"})
        body = _body_bytes(
            messages=[
                {"tool_calls": [{"function": {"arguments": arguments}}]},
            ]
        )
        outcome = verify(body)
        assert outcome.original_absent is True
        assert outcome.replacement_present is True
        assert outcome.caught is True

    def test_non_json_arguments_field_is_not_structurally_valid(self) -> None:
        verify = key_presence(
            container_field_path=("messages", 0, "tool_calls", 0, "function", "arguments"),
            key="999912345676",
        )
        body = _body_bytes(
            messages=[
                {"tool_calls": [{"function": {"arguments": "{not valid json"}}]},
            ]
        )
        outcome = verify(body)
        assert outcome.structurally_valid_json is False
        assert outcome.caught is False
