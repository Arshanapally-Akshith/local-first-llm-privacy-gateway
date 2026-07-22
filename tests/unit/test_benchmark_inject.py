"""benchmarks.generate.inject: the slot-and-inject engine itself —
proving offsets are exact by construction on controlled, synthetic
templates, independent of the real, committed template set (which
`test_benchmark_templates.py` and `test_benchmark_build_dataset.py`
cover separately)."""

import random

import pytest

from benchmarks.generate.inject import fill_template
from benchmarks.generate.templates import CarrierTemplate


def test_single_slot_offsets_are_exact() -> None:
    template = CarrierTemplate("t1", "en", "Hello {PERSON}, welcome.")
    example = fill_template(template, random.Random(0), "ex-1")
    assert len(example.entities) == 1
    entity = example.entities[0]
    assert example.text[entity.start : entity.end] == entity.value
    assert example.text.startswith("Hello ")
    assert example.text.endswith(", welcome.")


def test_multiple_slots_have_sequential_non_overlapping_offsets() -> None:
    template = CarrierTemplate("t2", "en", "{PERSON} works at {ORG} in {ADDRESS}.")
    example = fill_template(template, random.Random(0), "ex-2")
    assert len(example.entities) == 3
    for entity in example.entities:
        assert example.text[entity.start : entity.end] == entity.value
    # Non-overlapping and left-to-right in the order the slots appear.
    for earlier, later in zip(example.entities, example.entities[1:]):
        assert earlier.end <= later.start


def test_no_slots_leaves_text_unchanged() -> None:
    template = CarrierTemplate("t3", "en", "No entities here at all.")
    example = fill_template(template, random.Random(0), "ex-3")
    assert example.text == "No entities here at all."
    assert example.entities == ()


def test_unknown_slot_name_raises_value_error() -> None:
    template = CarrierTemplate("t4", "en", "Bad slot: {NOT_A_REAL_TYPE}.")
    with pytest.raises(ValueError, match="NOT_A_REAL_TYPE"):
        fill_template(template, random.Random(0), "ex-4")


def test_filled_text_contains_no_leftover_slot_braces() -> None:
    template = CarrierTemplate("t5", "en", "{PERSON} and {ORG} and {AADHAAR}.")
    example = fill_template(template, random.Random(0), "ex-5")
    assert "{" not in example.text
    assert "}" not in example.text


def test_example_id_and_metadata_are_carried_through() -> None:
    template = CarrierTemplate("t6", "hi_en", "{PHONE} pe call karo.")
    example = fill_template(template, random.Random(0), "ex-6")
    assert example.example_id == "ex-6"
    assert example.template_id == "t6"
    assert example.language == "hi_en"


def test_same_rng_state_produces_the_same_example() -> None:
    template = CarrierTemplate("t7", "en", "Card {CARD}, email {EMAIL}.")
    first = fill_template(template, random.Random(99), "ex-7")
    second = fill_template(template, random.Random(99), "ex-7")
    assert first == second
