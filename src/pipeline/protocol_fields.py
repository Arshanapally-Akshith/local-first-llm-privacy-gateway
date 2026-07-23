"""Protocol Enum Fields — the OpenAI wire protocol's closed-vocabulary
positions, exempted from PII detection by value membership, not by key
name.

`field_walker.walk()` finds every text-bearing field in a request body
without regard for what the field means (its own docstring: "no field
is special-cased by name" beyond the `arguments` JSON-unwrap). Most of
those fields are natural-language content a Tier-2 model can
legitimately be asked about. A small number are not content at all:
they are tokens from a finite, protocol-defined vocabulary.
`messages[].role` is the only one demonstrated to matter so far
(`docs/LIMITATIONS.md`, "Tier-2 can misclassify a message's literal
`role` field as `PERSON`" — a context-free four-character string like
"user" is exactly the input zero-shot NER is least reliable on).

The exemption this module grants is deliberately narrow and two-part: a
candidate region must (1) sit at a declared protocol-field path *and*
(2) hold a value that is actually one of that field's declared legal
members. Position alone is never sufficient — a value at a declared
path that is *not* a legal member (a malformed client, or an attempt to
smuggle real content into a position assumed safe to skip) falls
through to ordinary detection, exactly like any other field. That value
check is what makes the exemption safe to grant without opening a new
leak channel: it narrows *which values* count as protocol metadata,
rather than trusting a field's name alone to mean its content can never
be natural language.

Deliberately not attempted here: the recursive JSON-Schema `"type"`
keyword inside `tools[].function.parameters` (arbitrary nesting depth,
and can collide with a user-defined property literally named `type` —
no fixed path exists to declare it against). It remains ordinary
scanned text, same as it is today. Extending `_PROTOCOL_ENUM_FIELDS` to
a new position requires a demonstrated failing test or a real observed
bug, the same bar `messages[].role` itself met — not speculative
coverage of every field this schema could ever contain.
"""

from dataclasses import dataclass
from typing import Final

from src.pipeline.field_walker import FieldPath


class _AnyIndex:
    """Sentinel matching any list index in a `ProtocolEnumField.path_pattern`.

    A protocol field's *position* in the tree is fixed by the wire
    format (every message has a `role`), but which list index it lives
    at within `messages` is not — this stands in for "any index" at
    exactly the segments of a path that come from a list, the same way
    `field_walker.FieldPath` itself uses a plain `int` for those
    segments.
    """

    __slots__ = ()

    def __repr__(self) -> str:
        return "<any index>"


ANY_INDEX: Final[_AnyIndex] = _AnyIndex()

PathPattern = tuple[str | _AnyIndex, ...]
"""Like `field_walker.FieldPath`, but a segment may be `ANY_INDEX`
instead of a literal `int`, to match a field at any position within a
list rather than one specific index."""


@dataclass(frozen=True, slots=True)
class ProtocolEnumField:
    """One position in the wire protocol whose value is drawn from a
    small, closed, spec-defined vocabulary — not natural-language
    content — together with that vocabulary and where it comes from.
    `citation` exists so every entry in `_PROTOCOL_ENUM_FIELDS` is
    individually auditable against the spec it claims to describe
    (CLAUDE.md: "no magic constants... a comment stating where the
    value came from")."""

    path_pattern: PathPattern
    allowed_values: frozenset[str]
    citation: str


_PROTOCOL_ENUM_FIELDS: Final[tuple[ProtocolEnumField, ...]] = (
    ProtocolEnumField(
        path_pattern=("messages", ANY_INDEX, "role"),
        allowed_values=frozenset({"system", "user", "assistant", "tool", "function"}),
        citation=(
            "OpenAI chat completions request schema: messages[].role — "
            'the exact defect this closes is documented in docs/LIMITATIONS.md, '
            '"Tier-2 can misclassify a message\'s literal `role` field as `PERSON`"'
        ),
    ),
)


def is_protocol_enum_value(path: FieldPath, text: str) -> bool:
    """True iff `path` matches a declared `ProtocolEnumField` position
    *and* `text` is actually one of that field's declared legal values.

    A path match paired with a non-member value returns `False`, on
    purpose: see the module docstring for why the value check, not the
    path check alone, is what keeps this exemption from becoming a new
    leak channel. Callers that get `False` back must run detection on
    `text` exactly as they would for any other region.
    """
    return any(
        text in field.allowed_values and _matches(path, field.path_pattern)
        for field in _PROTOCOL_ENUM_FIELDS
    )


def _matches(path: FieldPath, pattern: PathPattern) -> bool:
    if len(path) != len(pattern):
        return False
    return all(
        segment is ANY_INDEX or segment == actual
        for segment, actual in zip(pattern, path, strict=True)
    )
