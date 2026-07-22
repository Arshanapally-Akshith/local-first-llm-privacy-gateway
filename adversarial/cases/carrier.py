"""Shared request-body construction for the slot-based bypass classes:
7 of the 9 (`spaced_digits`, `number_words`, `base64_encoding`,
`pii_in_code`, `homoglyphs`, `zero_width`, `transliterated_names`) plus
the `"clean"` variant of the remaining two (`split_across_turns`,
`pii_in_json_key`, which build their own structurally distinct
`"adversarial"` bodies directly, since neither fits "one entity in one
slot" — see each module's own docstring).
"""

from typing import Final

from src.core.types import EntityType
from src.pipeline.field_walker import FieldPath, JSONValue

from adversarial.cases.case_types import AdversarialCase, CaseLabel, ExpectedOutcome
from adversarial.cases.verify import slot_replacement

_MODEL: Final[str] = "gpt-4"
_CONTENT_FIELD_PATH: Final[FieldPath] = ("messages", 0, "content")


def single_user_message_body(text: str) -> JSONValue:
    """The plainest possible chat-completion request: one user turn,
    non-streaming (simplifies capture/verification — no SSE framing to
    parse; `sanitize()` runs identically regardless of `stream`)."""
    return {
        "model": _MODEL,
        "messages": [{"role": "user", "content": text}],
        "stream": False,
    }


def build_slot_case(
    *,
    case_id: str,
    bypass_class: str,
    entity_type: EntityType,
    label: CaseLabel,
    prefix: str,
    embedded_value: str,
    suffix: str,
    real_value: str,
    expected_outcome: ExpectedOutcome,
) -> AdversarialCase:
    """Build one slot-based case: a single user message whose content
    is `prefix + embedded_value + suffix`.

    For `label="clean"`, `embedded_value` is normally `real_value`
    itself (the canonical, unobfuscated form). For `label="adversarial"`,
    `embedded_value` is whatever transformed text the calling module's
    bypass mechanism produces (spaced, base64-encoded, homoglyph-
    substituted, ...) — `real_value` stays the true plaintext value in
    both cases, since that's what `verify.slot_replacement()` checks is
    absent from what upstream received, regardless of how it was
    embedded on the way in.
    """
    text = prefix + embedded_value + suffix
    body = single_user_message_body(text)
    verifier = slot_replacement(
        field_path=_CONTENT_FIELD_PATH,
        prefix=prefix,
        suffix=suffix,
        real_value=real_value,
        sent_value=embedded_value,
    )
    return AdversarialCase(
        case_id=case_id,
        bypass_class=bypass_class,
        entity_type=entity_type,
        label=label,
        request_body=body,
        expected_outcome=expected_outcome,
        verify=verifier,
    )
