"""Body Field Walker: walk() enumeration and rebuild() reconstruction,
tested as pure structural primitives — no detectors, no surrogates,
no security policy. `rebuild()` never raises on an unmatched
substitution path; it reports what it applied via
`RebuildResult.applied_paths` and leaves the caller to decide whether
a mismatch matters.
"""

import json

from src.pipeline.field_walker import FieldPath, JSONValue, TextRegion, rebuild, walk


def _region_map(regions: list[TextRegion]) -> dict[tuple[object, ...], str]:
    return {region.path: region.text for region in regions}


def test_walk_finds_content_across_all_message_roles() -> None:
    body: JSONValue = {
        "messages": [
            {"role": "system", "content": "be helpful and concise"},
            {"role": "user", "content": "hello there"},
            {"role": "assistant", "content": "hi, how can I help?"},
            {"role": "tool", "content": "42 degrees celsius"},
        ]
    }

    regions = _region_map(walk(body))

    assert regions[("messages", 0, "content")] == "be helpful and concise"
    assert regions[("messages", 1, "content")] == "hello there"
    assert regions[("messages", 2, "content")] == "hi, how can I help?"
    assert regions[("messages", 3, "content")] == "42 degrees celsius"


def test_walk_finds_name_field() -> None:
    body: JSONValue = {"messages": [{"role": "user", "name": "Priya Sharma", "content": "hi"}]}

    regions = _region_map(walk(body))

    assert regions[("messages", 0, "name")] == "Priya Sharma"


def test_walk_finds_strings_nested_in_tool_parameters_json_schema() -> None:
    body: JSONValue = {
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "lookup_pan",
                    "description": "Look up a taxpayer's PAN by name",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "the taxpayer's full name"}
                        },
                    },
                },
            }
        ]
    }

    regions = _region_map(walk(body))

    assert regions[("tools", 0, "function", "description")] == "Look up a taxpayer's PAN by name"
    assert (
        regions[("tools", 0, "function", "parameters", "properties", "name", "description")]
        == "the taxpayer's full name"
    )


def test_walk_unwraps_valid_json_object_arguments_into_sub_region_paths() -> None:
    body: JSONValue = {
        "messages": [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": json.dumps({"city": "Hyderabad"}),
                        },
                    }
                ],
            }
        ]
    }

    regions = _region_map(walk(body))
    args_path = ("messages", 0, "tool_calls", 0, "function", "arguments")

    assert args_path not in regions  # unwrapped, not present as a whole-string region
    assert regions[(*args_path, "city")] == "Hyderabad"


def test_walk_treats_malformed_json_arguments_as_one_opaque_region() -> None:
    body: JSONValue = {
        "messages": [
            {
                "role": "assistant",
                "tool_calls": [
                    {"function": {"name": "f", "arguments": "{not valid json"}},
                ],
            }
        ]
    }

    regions = _region_map(walk(body))
    args_path = ("messages", 0, "tool_calls", 0, "function", "arguments")

    assert regions[args_path] == "{not valid json"


def test_walk_treats_scalar_json_arguments_as_one_opaque_region() -> None:
    scalar_arguments = json.dumps("just a plain string, not an object")
    body: JSONValue = {
        "messages": [
            {
                "role": "assistant",
                "tool_calls": [{"function": {"name": "f", "arguments": scalar_arguments}}],
            }
        ]
    }

    regions = _region_map(walk(body))
    args_path = ("messages", 0, "tool_calls", 0, "function", "arguments")

    assert regions[args_path] == scalar_arguments


def test_walk_skips_none_content() -> None:
    body: JSONValue = {"messages": [{"role": "assistant", "content": None, "tool_calls": []}]}

    regions = _region_map(walk(body))

    assert ("messages", 0, "content") not in regions


def test_walk_includes_empty_string_content_as_a_region() -> None:
    body: JSONValue = {"messages": [{"role": "user", "content": ""}]}

    regions = _region_map(walk(body))

    assert regions[("messages", 0, "content")] == ""


def test_walk_skips_non_string_scalars() -> None:
    body: JSONValue = {"temperature": 0.7, "stream": True, "max_tokens": 256, "n": None}

    regions = walk(body)

    assert regions == []


def test_walk_does_not_mutate_input_body() -> None:
    body: JSONValue = {"messages": [{"role": "user", "content": "hello"}]}
    import copy

    original = copy.deepcopy(body)

    walk(body)

    assert body == original


def test_walk_paths_are_unique_across_a_complex_body() -> None:
    body: JSONValue = {
        "messages": [
            {"role": "system", "content": "sys"},
            {"role": "user", "name": "A", "content": "hi"},
            {
                "role": "assistant",
                "tool_calls": [
                    {"function": {"name": "f1", "arguments": json.dumps({"x": "1"})}},
                    {"function": {"name": "f2", "arguments": json.dumps({"y": "2"})}},
                ],
            },
        ],
        "tools": [{"function": {"name": "f1", "description": "d1"}}],
    }

    paths = [region.path for region in walk(body)]

    assert len(paths) == len(set(paths))


def test_rebuild_applies_plain_text_substitution_at_exact_path() -> None:
    body: JSONValue = {"messages": [{"role": "user", "content": "hello"}]}
    path = ("messages", 0, "content")

    result = rebuild(body, {path: "REDACTED"})

    assert result.body["messages"][0]["content"] == "REDACTED"  # type: ignore[index,call-overload]
    assert result.applied_paths == frozenset({path})


def test_rebuild_applies_substitution_inside_arguments_and_reserializes() -> None:
    body: JSONValue = {
        "messages": [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "get_weather",
                            "arguments": json.dumps({"city": "Delhi"}),
                        }
                    }
                ],
            }
        ]
    }
    path = ("messages", 0, "tool_calls", 0, "function", "arguments", "city")

    result = rebuild(body, {path: "REDACTED_CITY"})

    new_args = result.body["messages"][0]["tool_calls"][0]["function"]["arguments"]  # type: ignore[index,call-overload]
    assert json.loads(new_args) == {"city": "REDACTED_CITY"}  # type: ignore[arg-type]
    assert result.applied_paths == frozenset({path})


def test_rebuild_preserves_key_order_when_reserializing_arguments() -> None:
    body: JSONValue = {
        "messages": [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "f",
                            "arguments": json.dumps({"z": "1", "a": "2", "m": "3"}),
                        }
                    }
                ],
            }
        ]
    }
    path = ("messages", 0, "tool_calls", 0, "function", "arguments", "a")

    result = rebuild(body, {path: "CHANGED"})

    new_args = result.body["messages"][0]["tool_calls"][0]["function"]["arguments"]  # type: ignore[index,call-overload]
    assert list(json.loads(new_args).keys()) == ["z", "a", "m"]  # type: ignore[arg-type]


def test_rebuild_leaves_untouched_arguments_field_byte_identical() -> None:
    original_args = json.dumps({"symbol": "TCS"})
    body: JSONValue = {
        "messages": [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "get_weather",
                            "arguments": json.dumps({"city": "Delhi"}),
                        }
                    },
                    {"function": {"name": "get_stock", "arguments": original_args}},
                ],
            }
        ]
    }
    city_path = ("messages", 0, "tool_calls", 0, "function", "arguments", "city")

    result = rebuild(body, {city_path: "REDACTED_CITY"})

    untouched_args = result.body["messages"][0]["tool_calls"][1]["function"]["arguments"]  # type: ignore[index,call-overload]
    assert untouched_args is original_args  # the exact same string object, not just equal


def test_rebuild_with_empty_substitutions_is_structurally_equivalent_to_original() -> None:
    body: JSONValue = {
        "messages": [
            {"role": "system", "content": "sys"},
            {
                "role": "assistant",
                "tool_calls": [{"function": {"name": "f", "arguments": json.dumps({"x": "1"})}}],
            },
        ]
    }

    result = rebuild(body, {})

    assert result.body == body
    assert result.applied_paths == frozenset()


def test_rebuild_does_not_mutate_input_body() -> None:
    body: JSONValue = {"messages": [{"role": "user", "content": "hello"}]}
    import copy

    original = copy.deepcopy(body)

    rebuild(body, {("messages", 0, "content"): "REDACTED"})

    assert body == original


def test_rebuild_reports_unmatched_substitution_path_without_raising() -> None:
    body: JSONValue = {"messages": [{"role": "user", "content": "hello"}]}
    real_path = ("messages", 0, "content")
    fake_path = ("messages", 99, "content")

    result = rebuild(body, {real_path: "REDACTED", fake_path: "unreachable"})

    assert result.applied_paths == frozenset({real_path})
    assert result.body["messages"][0]["content"] == "REDACTED"  # type: ignore[index,call-overload]


def test_walk_rebuild_round_trip_preserves_path_set_and_only_changes_substituted_text() -> None:
    body: JSONValue = {
        "messages": [
            {"role": "system", "content": "be helpful"},
            {"role": "user", "name": "Priya Sharma", "content": "what's my PAN status"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"function": {"name": "lookup", "arguments": json.dumps({"pan": "ABCPE1234F"})}}
                ],
            },
        ]
    }
    pan_path: FieldPath = ("messages", 2, "tool_calls", 0, "function", "arguments", "pan")

    original_regions = _region_map(walk(body))
    substitutions: dict[FieldPath, str] = {pan_path: "XYZQR5678K"}

    result = rebuild(body, substitutions)
    new_regions = _region_map(walk(result.body))

    assert set(new_regions.keys()) == set(original_regions.keys())
    for path, original_text in original_regions.items():
        if path == pan_path:
            assert new_regions[path] == "XYZQR5678K"
        else:
            assert new_regions[path] == original_text


def test_multiple_independent_arguments_fields_unwrap_and_rebuild_independently() -> None:
    body: JSONValue = {
        "messages": [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "get_weather",
                            "arguments": json.dumps({"city": "Hyderabad"}),
                        },
                    },
                    {
                        "id": "call_2",
                        "function": {
                            "name": "get_stock",
                            "arguments": json.dumps({"symbol": "TCS"}),
                        },
                    },
                ],
            }
        ]
    }
    city_path = ("messages", 0, "tool_calls", 0, "function", "arguments", "city")
    symbol_path = ("messages", 0, "tool_calls", 1, "function", "arguments", "symbol")

    # Each unwraps independently at distinct paths.
    regions = _region_map(walk(body))
    assert regions[city_path] == "Hyderabad"
    assert regions[symbol_path] == "TCS"

    # Substituting only the first leaves the second's raw string untouched...
    original_symbol_args = body["messages"][0]["tool_calls"][1]["function"]["arguments"]  # type: ignore[index,call-overload]
    result = rebuild(body, {city_path: "REDACTED_CITY"})

    rebuilt_city_args = result.body["messages"][0]["tool_calls"][0]["function"]["arguments"]  # type: ignore[index,call-overload]
    rebuilt_symbol_args = result.body["messages"][0]["tool_calls"][1]["function"]["arguments"]  # type: ignore[index,call-overload]

    assert json.loads(rebuilt_city_args) == {"city": "REDACTED_CITY"}  # type: ignore[arg-type]
    assert rebuilt_symbol_args is original_symbol_args
    assert result.applied_paths == frozenset({city_path})

    # ...and substituting both rebuilds each independently, correctly.
    both_result = rebuild(body, {city_path: "REDACTED_CITY", symbol_path: "REDACTED_SYMBOL"})
    both_city_args = both_result.body["messages"][0]["tool_calls"][0]["function"]["arguments"]  # type: ignore[index,call-overload]
    both_symbol_args = both_result.body["messages"][0]["tool_calls"][1]["function"]["arguments"]  # type: ignore[index,call-overload]

    assert json.loads(both_city_args) == {"city": "REDACTED_CITY"}  # type: ignore[arg-type]
    assert json.loads(both_symbol_args) == {"symbol": "REDACTED_SYMBOL"}  # type: ignore[arg-type]
    assert both_result.applied_paths == frozenset({city_path, symbol_path})


def test_empty_body_returns_no_regions() -> None:
    assert walk({}) == []
