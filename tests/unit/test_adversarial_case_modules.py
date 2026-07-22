"""One test class per bypass-class module, proving the obfuscation
transform actually does what its module docstring claims, directly
against the real Tier-1 detectors — fast, no live gateway, no model
load (mirrors this suite's own "measure, don't assume" discipline that
was already applied once, empirically, before any of these modules
were written).

Does not re-verify what `tests/unit/test_adversarial_verify.py` and
`test_adversarial_carrier.py` already cover generically (prefix/suffix
invariance, the three-signal `caught` criterion) — only what is
specific to each module: that its `build_cases()` output actually
contains the obfuscation it claims to, and that the obfuscation really
does defeat (or, for the one Tier-2 class, is *predicted* to defeat)
the relevant real detector.
"""

import json
import random

from src.detect import precedence
from src.detect.registry import get_tier1_detectors
from src.pipeline.field_walker import walk
from src.session.names import DEFAULT_NAME_CANDIDATES

import benchmarks.generate.entity_values as benchmark_entity_values
from adversarial.cases import (
    base64_encoding,
    homoglyphs,
    number_words,
    pii_in_code,
    pii_in_json_key,
    spaced_digits,
    split_across_turns,
    transliterated_names,
    zero_width,
)


def _tier1_detects_anything(text: str) -> bool:
    spans_per_detector = [detector.detect(text) for detector in get_tier1_detectors()]
    return precedence.resolve(spans_per_detector) != []


def _content_of(case_request_body: object) -> str:
    regions = walk(case_request_body)  # type: ignore[arg-type]
    contents = [r.text for r in regions if r.path and r.path[-1] == "content"]
    assert len(contents) == 1
    return contents[0]


class TestSpacedDigits:
    def test_adversarial_cases_are_not_tier1_detectable(self) -> None:
        for case in spaced_digits.build_cases():
            if case.label != "adversarial":
                continue
            assert not _tier1_detects_anything(_content_of(case.request_body))

    def test_clean_cases_are_tier1_detectable(self) -> None:
        for case in spaced_digits.build_cases():
            if case.label != "clean":
                continue
            assert _tier1_detects_anything(_content_of(case.request_body))

    def test_spaced_helper_reinserts_only_spaces_and_stays_reversible(self) -> None:
        """Tests the transform function directly (isolated from any
        carrier text) rather than reverse-parsing a built case's full
        message content: stripping every space from `content` mid-body
        would also glue the surrounding carrier words to the digits,
        which breaks Tier-1's own `\\b` boundary for a *different*
        reason than spacing does — an unrelated ambiguity this test
        avoids entirely by checking the transform in isolation."""
        value = benchmark_entity_values.generate_value("AADHAAR", random.Random(1))
        spaced = spaced_digits._spaced(value)
        assert " " in spaced
        assert spaced.replace(" ", "") == value
        assert _tier1_detects_anything(value)
        assert not _tier1_detects_anything(spaced)


class TestNumberWords:
    def test_adversarial_cases_are_not_tier1_detectable(self) -> None:
        for case in number_words.build_cases():
            if case.label != "adversarial":
                continue
            assert not _tier1_detects_anything(_content_of(case.request_body))

    def test_clean_cases_are_tier1_detectable(self) -> None:
        for case in number_words.build_cases():
            if case.label != "clean":
                continue
            assert _tier1_detects_anything(_content_of(case.request_body))

    def test_adversarial_content_has_no_digits(self) -> None:
        for case in number_words.build_cases():
            if case.label == "adversarial":
                content = _content_of(case.request_body)
                assert not any(char.isdigit() for char in content)


class TestPiiInCode:
    def test_adversarial_cases_are_not_tier1_detectable(self) -> None:
        for case in pii_in_code.build_cases():
            if case.label != "adversarial":
                continue
            assert not _tier1_detects_anything(_content_of(case.request_body))

    def test_clean_cases_are_tier1_detectable(self) -> None:
        for case in pii_in_code.build_cases():
            if case.label != "clean":
                continue
            assert _tier1_detects_anything(_content_of(case.request_body))

    def test_adversarial_content_embeds_value_adjacent_to_underscore(self) -> None:
        for case in pii_in_code.build_cases():
            if case.label == "adversarial":
                assert "_" in _content_of(case.request_body)


class TestBase64Encoding:
    def test_adversarial_cases_are_not_tier1_detectable(self) -> None:
        for case in base64_encoding.build_cases():
            if case.label != "adversarial":
                continue
            assert not _tier1_detects_anything(_content_of(case.request_body))

    def test_clean_cases_are_tier1_detectable(self) -> None:
        for case in base64_encoding.build_cases():
            if case.label != "clean":
                continue
            assert _tier1_detects_anything(_content_of(case.request_body))


class TestZeroWidth:
    def test_adversarial_cases_are_not_tier1_detectable(self) -> None:
        for case in zero_width.build_cases():
            if case.label != "adversarial":
                continue
            assert not _tier1_detects_anything(_content_of(case.request_body))

    def test_clean_cases_are_tier1_detectable(self) -> None:
        for case in zero_width.build_cases():
            if case.label != "clean":
                continue
            assert _tier1_detects_anything(_content_of(case.request_body))

    def test_zero_width_space_constant_is_actually_u_plus_200b(self) -> None:
        assert ord(zero_width._ZERO_WIDTH_SPACE) == 0x200B


class TestHomoglyphs:
    def test_adversarial_cases_are_not_tier1_detectable(self) -> None:
        for case in homoglyphs.build_cases():
            if case.label != "adversarial":
                continue
            assert not _tier1_detects_anything(_content_of(case.request_body))

    def test_clean_cases_are_tier1_detectable(self) -> None:
        for case in homoglyphs.build_cases():
            if case.label != "clean":
                continue
            assert _tier1_detects_anything(_content_of(case.request_body))

    def test_adversarial_content_contains_no_ascii_replacement_of_first_letter(self) -> None:
        """The substituted character must genuinely be non-ASCII (a
        real homoglyph), not accidentally still a plain Latin letter."""
        for case in homoglyphs.build_cases():
            if case.label != "adversarial":
                continue
            content = _content_of(case.request_body)
            non_ascii = [char for char in content if ord(char) > 127]
            assert len(non_ascii) == 1


class TestSplitAcrossTurns:
    def test_adversarial_fragments_are_individually_undetectable(self) -> None:
        for case in split_across_turns.build_cases():
            if case.label != "adversarial":
                continue
            body = case.request_body
            assert isinstance(body, dict)
            messages = body["messages"]
            assert isinstance(messages, list)
            # messages[0] and messages[2] are the two user turns carrying
            # one fragment each; messages[1] is the no-PII assistant reply.
            assert len(messages) == 3
            for index in (0, 2):
                message = messages[index]
                assert isinstance(message, dict)
                fragment_text = message["content"]
                assert isinstance(fragment_text, str)
                assert not _tier1_detects_anything(fragment_text)

    def test_clean_case_is_tier1_detectable(self) -> None:
        for case in split_across_turns.build_cases():
            if case.label == "clean":
                assert _tier1_detects_anything(_content_of(case.request_body))


class TestPiiInJsonKey:
    def test_adversarial_value_is_used_as_a_dict_key_not_a_value(self) -> None:
        for case in pii_in_json_key.build_cases():
            if case.label != "adversarial":
                continue
            body = case.request_body
            assert isinstance(body, dict)
            messages = body["messages"]
            assert isinstance(messages, list)
            first_message = messages[0]
            assert isinstance(first_message, dict)
            tool_calls = first_message["tool_calls"]
            assert isinstance(tool_calls, list)
            first_tool_call = tool_calls[0]
            assert isinstance(first_tool_call, dict)
            function = first_tool_call["function"]
            assert isinstance(function, dict)
            arguments_raw = function["arguments"]
            assert isinstance(arguments_raw, str)
            arguments = json.loads(arguments_raw)
            assert isinstance(arguments, dict)
            assert len(arguments) == 1
            ((key, _value),) = arguments.items()
            # the entity value must be the key, and must not appear as a value
            assert key not in arguments.values()


class TestTransliteratedNames:
    def test_clean_and_adversarial_embed_different_scripts(self) -> None:
        for case in transliterated_names.build_cases():
            content = _content_of(case.request_body)
            has_non_ascii = any(ord(char) > 127 for char in content)
            if case.label == "clean":
                assert not has_non_ascii
            else:
                assert has_non_ascii

    def test_name_pairs_are_drawn_from_the_gateways_own_candidate_pool(self) -> None:
        for latin_name, _devanagari_name in transliterated_names._NAME_PAIRS:
            assert latin_name in DEFAULT_NAME_CANDIDATES
