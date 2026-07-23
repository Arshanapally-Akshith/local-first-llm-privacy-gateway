"""pipeline.protocol_fields: `is_protocol_enum_value()` as a pure
structural + value predicate — no detectors, no sanitize(), no
network. Mirrors `test_field_walker.py`'s style: these prove the
predicate itself, in isolation, before `test_sanitize.py` proves it
wired correctly into the pipeline.
"""

import pytest

from src.pipeline.protocol_fields import is_protocol_enum_value


@pytest.mark.parametrize("role", ["system", "user", "assistant", "tool", "function"])
def test_true_for_every_legal_role_value_at_the_role_path(role: str) -> None:
    assert is_protocol_enum_value(("messages", 0, "role"), role) is True


@pytest.mark.parametrize("index", [0, 1, 41])
def test_true_for_role_value_at_any_message_index(index: int) -> None:
    assert is_protocol_enum_value(("messages", index, "role"), "user") is True


def test_false_for_non_enum_text_at_the_role_path() -> None:
    """The fail-safe case this whole module exists for: a value at the
    role position that is *not* a legal role must still be scanned like
    ordinary content — this is what stops the exemption from becoming a
    new leak channel (see the module docstring)."""
    assert is_protocol_enum_value(("messages", 0, "role"), "Krishna Chowdhury") is False


def test_false_for_a_legal_role_string_appearing_in_content() -> None:
    """Position matters, not just string equality: the literal word
    "user" in a message's `content` is ordinary text and must not be
    exempted just because it happens to equal a legal role value."""
    assert is_protocol_enum_value(("messages", 0, "content"), "user") is False


def test_false_for_a_legal_role_string_in_a_name_field() -> None:
    assert is_protocol_enum_value(("messages", 0, "name"), "user") is False


def test_false_for_role_nested_one_level_deeper_than_declared() -> None:
    assert is_protocol_enum_value(("messages", 0, "extra", "role"), "user") is False


def test_false_for_role_missing_the_message_index_segment() -> None:
    assert is_protocol_enum_value(("messages", "role"), "user") is False


def test_false_for_an_unrelated_type_field_deep_in_a_json_schema() -> None:
    """Deliberate non-goal (module docstring): the recursive JSON-Schema
    `"type"` keyword inside `tools[].function.parameters` has no
    declared entry, so it is never exempted — proving no unintended
    over-reach beyond the declared table."""
    path = (
        "tools",
        0,
        "function",
        "parameters",
        "properties",
        "type",
        "type",
    )
    assert is_protocol_enum_value(path, "string") is False


def test_false_for_empty_path() -> None:
    assert is_protocol_enum_value((), "user") is False
