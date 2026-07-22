"""Three verifier builders, shared by every bypass-class module,
producing the `VerificationOutcome` triple `case_types.py` documents.
Each builder returns a closure over the specifics of one case — no
verifier reads or hardcodes anything about the surrogate scheme itself
(CLAUDE.md: "do not hardcode specific surrogate values").

`slot_replacement()` covers 7 of the 9 bypass classes plus both
"clean" variants of the remaining two: one entity value sits inside
one text field, and the surrounding carrier text is known exactly, so
"a replacement happened" can be proven generically by checking that
the text immediately before and after the entity's known position is
untouched while the text between those two anchors changed to
something that is not the original value — regardless of what that
something is.

`fragment_reconstruction()` and `key_presence()` cover the two
bypasses ARCHITECTURE.md calls out as existing "only at the system
level" (split-across-turns, PII-as-a-JSON-key): there is no single slot
to check prefix/suffix invariance around, because the entity was never
assembled into one contiguous span in the first place. For these two,
`replacement_present` collapses to the same signal as `original_absent`
— see each function's own docstring for why that is the correct,
honest measurement rather than a simplification.
"""

import json
from collections.abc import Callable, Sequence

from src.pipeline.field_walker import FieldPath, JSONValue

from adversarial.cases.case_types import VerificationOutcome


def _decode(captured: bytes) -> tuple[str | None, JSONValue | None, str | None]:
    """Shared prelude for every verifier: decode as UTF-8, then parse
    as JSON. Returns `(text, parsed, error)` — exactly one of `parsed`
    or `error` is non-`None` when `text` is not `None`; all three are
    `None` only if decoding itself failed, in which case `error` holds
    the reason instead."""
    try:
        text = captured.decode("utf-8")
    except UnicodeDecodeError as exc:
        return None, None, f"captured upstream body is not valid utf-8: {exc}"
    try:
        parsed: JSONValue = json.loads(text)
    except json.JSONDecodeError as exc:
        return text, None, f"captured upstream body is not valid JSON: {exc}"
    return text, parsed, None


def _get_at_path(value: JSONValue, path: FieldPath) -> JSONValue:
    """Navigate `path` from `value`'s root. Raises `KeyError`/`IndexError`/
    `TypeError` on a path that doesn't match the body's actual shape —
    the caller treats any of these as "field not found," which is
    itself a verification failure worth surfacing in `detail`, not a
    Python exception escaping into the test/runner."""
    for segment in path:
        if isinstance(segment, str) and isinstance(value, dict):
            value = value[segment]
        elif isinstance(segment, int) and isinstance(value, list):
            value = value[segment]
        else:
            raise TypeError(
                f"path segment {segment!r} does not match body shape {type(value).__name__}"
            )
    return value


def slot_replacement(
    *, field_path: FieldPath, prefix: str, suffix: str, real_value: str, sent_value: str
) -> Callable[[bytes], VerificationOutcome]:
    """Build a verifier for a case where `sent_value` (the literal text
    actually placed in the request — canonical for a "clean" case,
    obfuscated for most "adversarial" cases) was embedded at exactly
    one field, between a known `prefix` and `suffix` of surrounding
    carrier text that sanitization must never touch. `real_value` is
    the true, always-plaintext-canonical entity — identical to
    `sent_value` for a "clean" case, but *not* for an obfuscated one
    (e.g. `sent_value` is a base64 blob; `real_value` is the digits it
    encodes).

    `original_absent` is checked against the *entire* captured body,
    not just the one field — a stronger, more robust guarantee than a
    field-local check, and immune to `field_walker.rebuild()`'s own
    freedom to move substituted text within the field as long as the
    field itself is reachable at `field_path`.

    `replacement_present` requires the field to still start with
    `prefix` and end with `suffix` (proving the *carrier* text is
    untouched — a targeted substitution, not a blanket redaction or a
    truncated/corrupted field) and requires the text between those two
    anchors to be non-empty and different from `sent_value` — proving
    something *changed relative to what was actually sent*, without
    ever checking what it changed to. Comparing against `sent_value`
    here, not `real_value`, is load-bearing: for an obfuscated case,
    `sent_value != real_value` by construction (that's the whole
    obfuscation), so comparing the surviving middle text against
    `real_value` would wrongly read "unchanged, still-obfuscated text"
    as if a replacement had occurred, defeating the very success
    criterion this function exists to enforce.
    """

    def _verify(captured: bytes) -> VerificationOutcome:
        text, parsed, error = _decode(captured)
        if text is None or (parsed is None and error is not None and "utf-8" in error):
            return VerificationOutcome(False, False, False, error or "decode failed")
        if parsed is None:
            return VerificationOutcome(False, False, False, error or "JSON parse failed")

        original_absent = real_value not in text

        try:
            field_value = _get_at_path(parsed, field_path)
        except (KeyError, IndexError, TypeError) as exc:
            return VerificationOutcome(
                True, original_absent, False, f"field_path {field_path} not reachable: {exc}"
            )
        if not isinstance(field_value, str):
            return VerificationOutcome(
                True, original_absent, False, f"field at {field_path} is not a string"
            )

        prefix_ok = field_value.startswith(prefix)
        suffix_ok = field_value.endswith(suffix)
        if not (prefix_ok and suffix_ok):
            return VerificationOutcome(
                True,
                original_absent,
                False,
                f"surrounding carrier text changed unexpectedly at {field_path}",
            )
        middle = field_value[len(prefix) : len(field_value) - len(suffix)]
        replacement_present = len(middle) > 0 and middle != sent_value
        detail = (
            "prefix/suffix invariant held; sent value replaced"
            if replacement_present
            else "prefix/suffix invariant held; sent value unchanged"
        )
        return VerificationOutcome(True, original_absent, replacement_present, detail)

    return _verify


def fragment_reconstruction(
    fragments: Sequence[tuple[FieldPath, str]],
) -> Callable[[bytes], VerificationOutcome]:
    """Build a verifier for the split-across-turns class: `fragments`
    is the `(field_path, fragment_text)` pair for each half of an
    entity that was never assembled into one contiguous span by
    construction (each half lives in its own message/field).

    There is no "replacement" to prove here in the `slot_replacement()`
    sense — `field_walker.walk()` treats each message's `content` as an
    independent leaf and never concatenates across them, so neither
    fragment alone is a complete, canonical-form entity for any Tier-1
    detector to match (verified empirically per fragment before this
    class was written — see the module docstring of
    `split_across_turns.py`). "Caught" would require *some* mechanism
    to have altered at least one fragment; since none exists, the
    honest, single signal this function can measure is whether both
    fragments still cross to upstream byte-for-byte unchanged
    (`fragments_intact`) — if so, an attacker holding the full
    transcript can trivially reconstruct the real value by
    concatenation, which is exactly the leak this class exists to
    measure. `replacement_present` mirrors `original_absent` rather
    than being a separate, independent signal, because there is only
    one thing to observe: whether anything moved either fragment.
    """

    def _verify(captured: bytes) -> VerificationOutcome:
        text, parsed, error = _decode(captured)
        if text is None:
            return VerificationOutcome(False, False, False, error or "decode failed")
        if parsed is None:
            return VerificationOutcome(False, False, False, error or "JSON parse failed")

        fragments_intact = True
        for field_path, fragment_text in fragments:
            try:
                field_value = _get_at_path(parsed, field_path)
            except (KeyError, IndexError, TypeError) as exc:
                return VerificationOutcome(
                    True, False, False, f"fragment field_path {field_path} not reachable: {exc}"
                )
            if not isinstance(field_value, str) or fragment_text not in field_value:
                fragments_intact = False
                break

        reconstructable = fragments_intact
        return VerificationOutcome(
            True,
            not reconstructable,
            not reconstructable,
            f"fragments_intact={fragments_intact} "
            "(True means both halves crossed unchanged, making the full value "
            "trivially reconstructable from the transcript)",
        )

    return _verify


def key_presence(
    *, container_field_path: FieldPath, key: str
) -> Callable[[bytes], VerificationOutcome]:
    """Build a verifier for the PII-as-a-JSON-key class: `container_field_path`
    names a JSON-string field (e.g. a tool call's `arguments`) whose
    parsed content should be a JSON object; `key` is the entity value
    placed as one of that object's *keys* rather than a value.

    `field_walker._walk()` only ever recurses into dict *values*
    (`value.items()`, yielding each `child`) — it never visits or
    emits a `TextRegion` for a dict key itself, so nothing in the
    sanitize pipeline can ever detect or substitute a key. The only
    honest measurement here is whether `key` still appears, unmodified,
    among the container's keys after the round trip — if so, the
    gateway forwarded it exactly as sent, which is the leak this class
    measures. As with `fragment_reconstruction()`, there is no separate
    "replacement" signal to observe (nothing could have replaced a key
    this codebase never looks at), so `replacement_present` mirrors
    `original_absent`.
    """

    def _verify(captured: bytes) -> VerificationOutcome:
        text, parsed, error = _decode(captured)
        if text is None:
            return VerificationOutcome(False, False, False, error or "decode failed")
        if parsed is None:
            return VerificationOutcome(False, False, False, error or "JSON parse failed")

        try:
            container_raw = _get_at_path(parsed, container_field_path)
        except (KeyError, IndexError, TypeError) as exc:
            return VerificationOutcome(
                True, False, False, f"container field_path {container_field_path} not reachable: {exc}"
            )
        if not isinstance(container_raw, str):
            return VerificationOutcome(
                True, False, False, f"container field at {container_field_path} is not a string"
            )
        try:
            container = json.loads(container_raw)
        except json.JSONDecodeError as exc:
            return VerificationOutcome(False, False, False, f"container field is not valid JSON: {exc}")

        key_present = isinstance(container, dict) and key in container
        return VerificationOutcome(
            True,
            not key_present,
            not key_present,
            f"key_present={key_present} (True means the JSON key crossed unmodified)",
        )

    return _verify
