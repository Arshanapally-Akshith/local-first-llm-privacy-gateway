"""benchmarks.generate.build_dataset: the full generation pipeline,
exercised end to end — this is where BUILD.md's Phase 5 DoD item
("offset-integrity test passes on 100% of examples") and this task's
own requirements (offsets always correct, generated entities satisfy
required constraints, regeneration is deterministic) are proved against
the actual, full generated dataset, not just isolated units.
"""

import json

from src.core.types import ENTITY_TYPES, Offset, Span
from src.detect.registry import get_tier1_detectors
from src.session.candidates import NAME_MAP_ENTITY_TYPES, get_candidates

from benchmarks.generate.build_dataset import (
    _INSTANTIATIONS_PER_TEMPLATE,
    build_dataset,
    to_jsonl,
    write_jsonl,
)
from benchmarks.generate.templates import TEMPLATES

_TIER1_DETECTORS_BY_TYPE = {detector.entity_type: detector for detector in get_tier1_detectors()}

# Built once per test module run — pure computation, no I/O, no model:
# fast enough to share across every test below rather than rebuilding
# per test.
_DATASET = build_dataset()


def test_dataset_size_matches_build_mds_2_to_3k_target() -> None:
    expected = len(TEMPLATES) * _INSTANTIATIONS_PER_TEMPLATE
    assert len(_DATASET) == expected
    assert 2_000 <= len(_DATASET) <= 3_000, (
        f"{len(_DATASET)} examples falls outside BUILD.md's stated ~2-3k range"
    )


def test_example_ids_are_unique() -> None:
    ids = [example.example_id for example in _DATASET]
    assert len(ids) == len(set(ids))


def test_every_entity_type_appears_at_least_once() -> None:
    seen = {entity.entity_type for example in _DATASET for entity in example.entities}
    assert seen == set(ENTITY_TYPES)


def test_both_languages_appear() -> None:
    languages = {example.language for example in _DATASET}
    assert languages == {"en", "hi_en"}


def test_every_gold_offset_is_exact_on_100_percent_of_examples() -> None:
    checked = 0
    for example in _DATASET:
        for entity in example.entities:
            assert example.text[entity.start : entity.end] == entity.value
            checked += 1
    assert checked > 0


def test_structured_entities_are_detected_in_situ_by_the_real_detector() -> None:
    """Stronger than isolated-value validation
    (`test_benchmark_entity_values.py`): confirms the recorded gold
    span survives detection *within the full carrier sentence*, which
    is the only way to catch an injection-boundary mistake (e.g. a
    value glued to adjacent text in a way that breaks a detector's own
    word-boundary or lookaround assertion).
    """
    checked = 0
    for example in _DATASET:
        for entity in example.entities:
            if entity.entity_type not in _TIER1_DETECTORS_BY_TYPE:
                continue
            detector = _TIER1_DETECTORS_BY_TYPE[entity.entity_type]
            expected_span = Span(
                start=entity.start, end=entity.end, entity_type=entity.entity_type, tier=1
            )
            found = detector.detect(example.text)
            assert expected_span in found, (
                f"{entity.entity_type} gold span {entity.start}:{entity.end} in example "
                f"{example.example_id!r} (template {example.template_id!r}) was not "
                f"detected in situ: text={example.text!r}"
            )
            checked += 1
    assert checked > 0


def test_name_map_entities_are_drawn_from_the_real_candidate_pools() -> None:
    checked = 0
    for example in _DATASET:
        for entity in example.entities:
            if entity.entity_type not in NAME_MAP_ENTITY_TYPES:
                continue
            assert entity.value in get_candidates(entity.entity_type)
            checked += 1
    assert checked > 0


def test_build_dataset_is_deterministic_across_independent_calls() -> None:
    first = build_dataset()
    second = build_dataset()
    assert first == second
    assert to_jsonl(first) == to_jsonl(second)


def test_a_different_seed_produces_a_different_dataset() -> None:
    # Guards against a bug where `seed` is silently ignored and the
    # "determinism" test above would pass vacuously regardless.
    default = build_dataset()
    alternate = build_dataset(seed=999)
    assert default != alternate


def test_to_jsonl_round_trips_through_json() -> None:
    lines = to_jsonl(_DATASET).splitlines()
    assert len(lines) == len(_DATASET)
    for line, example in zip(lines, _DATASET):
        parsed = json.loads(line)
        assert parsed["example_id"] == example.example_id
        assert parsed["template_id"] == example.template_id
        assert parsed["language"] == example.language
        assert parsed["text"] == example.text
        assert len(parsed["entities"]) == len(example.entities)
        for parsed_entity, entity in zip(parsed["entities"], example.entities):
            assert parsed_entity["start"] == int(entity.start)
            assert parsed_entity["end"] == int(entity.end)
            assert parsed_entity["entity_type"] == entity.entity_type
            assert parsed_entity["value"] == entity.value


def test_write_jsonl_is_byte_identical_across_independent_writes(tmp_path):

    path_a = tmp_path / "a.jsonl"
    path_b = tmp_path / "b.jsonl"
    write_jsonl(build_dataset(), path_a)
    write_jsonl(build_dataset(), path_b)
    assert path_a.read_bytes() == path_b.read_bytes()


def test_gold_entity_offsets_never_exceed_text_length() -> None:
    for example in _DATASET:
        for entity in example.entities:
            assert Offset(0) <= entity.start
            assert entity.end <= len(example.text)
