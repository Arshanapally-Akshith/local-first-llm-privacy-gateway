"""benchmarks.generate.templates: static validation of the committed
carrier-sentence templates themselves — independent of any particular
generated example, so a template-authoring mistake (a typo'd slot name,
a duplicate slot type, a UPI/EMAIL-before-period hazard) is caught here
directly, not just incidentally by the dataset-level tests."""

import re
from collections import Counter

from src.core.types import ENTITY_TYPES

from benchmarks.generate.templates import TEMPLATES

_ANY_BRACE_TOKEN = re.compile(r"\{([^{}]*)\}")
_MIN_TEMPLATES_PER_TYPE = 2


def test_template_ids_are_unique() -> None:
    ids = [template.template_id for template in TEMPLATES]
    assert len(ids) == len(set(ids))


def test_every_brace_token_is_a_known_entity_type() -> None:
    """Catches a misspelled slot (e.g. `{ADRESS}`) that would otherwise
    silently survive `inject.py`'s `_SLOT_PATTERN.split()` as ordinary
    literal text with no gold span at all — `_SLOT_PATTERN` itself only
    ever matches `[A-Z_]+`, so it would never even notice a malformed
    token; this scan is deliberately broader (any `{...}`, not just
    ones shaped like a valid entity type) so it also catches a slot
    typo'd in lowercase or with stray punctuation.
    """
    for template in TEMPLATES:
        for token in _ANY_BRACE_TOKEN.findall(template.text):
            assert token in ENTITY_TYPES, (
                f"template {template.template_id!r} has a brace token {{{token}}} "
                f"that is not a known EntityType"
            )


def test_no_template_repeats_an_entity_type_in_two_slots() -> None:
    for template in TEMPLATES:
        tokens = _ANY_BRACE_TOKEN.findall(template.text)
        assert len(tokens) == len(set(tokens)), (
            f"template {template.template_id!r} repeats a slot type: {tokens}"
        )


def test_no_upi_or_email_slot_is_glued_directly_to_a_trailing_period() -> None:
    """`UpiDetector`/`EmailDetector` both use `(?!...)` lookaheads that
    specifically reject a literal `.` immediately after the token (see
    their module docstrings) — a template ending `...{UPI}.` with no
    separating text would generate a gold span the real detector could
    never find in situ. Every other entity type's plain `\\b` boundary
    tolerates a following period as an ordinary word boundary and has
    no equivalent hazard (see `templates.py`'s own module docstring).
    """
    for template in TEMPLATES:
        assert "{UPI}." not in template.text, template.template_id
        assert "{EMAIL}." not in template.text, template.template_id


def test_every_entity_type_appears_in_at_least_two_templates() -> None:
    counts: Counter[str] = Counter()
    for template in TEMPLATES:
        counts.update(_ANY_BRACE_TOKEN.findall(template.text))
    for entity_type in ENTITY_TYPES:
        assert counts[entity_type] >= _MIN_TEMPLATES_PER_TYPE, (
            f"{entity_type} appears in only {counts[entity_type]} template(s)"
        )


def test_every_template_declares_a_known_language() -> None:
    for template in TEMPLATES:
        assert template.language in ("en", "hi_en")


def test_both_languages_are_represented() -> None:
    languages = {template.language for template in TEMPLATES}
    assert languages == {"en", "hi_en"}
