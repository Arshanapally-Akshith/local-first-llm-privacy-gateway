"""Body Field Walker — enumerate and rebuild every text-bearing field
in a request body.

`walk()` finds every string in a request body that could carry PII —
system prompt, every message role, tool/function definitions,
tool-result messages, `name` fields, and (transparently unwrapped)
function-call arguments — and reports it with the exact structural
path to reach it again. `rebuild()` takes those paths back with new
text and returns a new body.

This module is a pure structural primitive and makes no security
judgment. If a caller-supplied substitution path doesn't correspond to
a real leaf, `rebuild()` simply doesn't apply it and says so via
`RebuildResult.applied_paths` — it does not raise. Deciding whether an
unmatched path means a substitution silently failed to reach the
network (a leak) is a policy question for whatever calls this module
(the pipeline, not yet built), not something the traversal primitive
itself should decide. Compare `applied_paths` against the substitution
keys you passed in; a mismatch is your signal to act on, not this
module's.

The only schema-specific behaviour here is unwrapping function-call
arguments: OpenAI encodes `...function.arguments` as a JSON string
rather than a nested object, so a value whose path's last segment is
literally `"arguments"` gets one transparent parse attempt. Every other
string field is treated as opaque text, deliberately: blanket
content-sniffing (attempting to JSON-parse *any* string anywhere)
would risk re-serializing a user's literal JSON-looking message text
with different formatting on rebuild, for no privacy benefit — the
string is scanned for PII either way, whether treated as one region or
several.
"""

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Final

FieldPath = tuple[str | int, ...]
"""The sequence of dict keys / list indices from the root of a request
body to one leaf value. A JSON-string boundary (see module docstring)
adds no path segment — it is transparent to path consumers. Since a
JSON body is a tree, every reachable position has exactly one path."""

JSONValue = dict[str, "JSONValue"] | list["JSONValue"] | str | int | float | bool | None
"""Any value that can appear in a `json.loads`-parsed request body."""

_ARGUMENTS_KEY: Final[str] = "arguments"


@dataclass(frozen=True, slots=True)
class TextRegion:
    """One leaf string found during a walk, and the path to reach it."""

    path: FieldPath
    text: str


@dataclass(frozen=True, slots=True)
class RebuildResult:
    """The output of `rebuild()`: a new body, plus which of the given
    substitution paths were actually matched to a real leaf and
    applied. See the module docstring for why this is a report, not a
    raised error, when `applied_paths != substitutions.keys()`."""

    body: JSONValue
    applied_paths: frozenset[FieldPath]


def walk(body: JSONValue) -> list[TextRegion]:
    """Enumerate every candidate text region in `body`.

    Walks every `dict`/`list` node generically — no field is special-
    cased by name beyond the `arguments` JSON-unwrap rule described in
    the module docstring — so a field this project's authors didn't
    anticipate is still found, not silently skipped. Does not mutate
    `body`. `int`/`float`/`bool`/`None` leaves are not string-valued
    and are never emitted or recursed into.
    """
    return list(_walk(body, ()))


def _walk(value: JSONValue, path: FieldPath) -> Iterator[TextRegion]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk(child, (*path, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk(item, (*path, index))
    elif isinstance(value, str):
        if path and path[-1] == _ARGUMENTS_KEY:
            parsed = _try_parse_json_container(value)
            if parsed is not None:
                yield from _walk(parsed, path)
                return
        yield TextRegion(path=path, text=value)
    # int, float, bool, None: not string-valued, nothing to find here.


def rebuild(body: JSONValue, substitutions: Mapping[FieldPath, str]) -> RebuildResult:
    """Return a new body with `substitutions` applied at their paths.

    Never mutates `body`; always returns a freshly built structure —
    see the module docstring's linked reasoning in ARCHITECTURE.md
    (a half-sanitized request must never be reachable through an
    in-place mutation left over from a crashed call).

    A JSON-string `arguments` field is only re-parsed and re-serialized
    if at least one substitution path falls underneath it; an
    `arguments` field with nothing to change inside it is returned as
    its original, byte-identical string — not needlessly reformatted
    by a no-op `json.loads`/`json.dumps` round trip.
    """
    applied: set[FieldPath] = set()
    new_body = _rebuild(body, (), substitutions, applied)
    return RebuildResult(body=new_body, applied_paths=frozenset(applied))


def _rebuild(
    value: JSONValue,
    path: FieldPath,
    substitutions: Mapping[FieldPath, str],
    applied: set[FieldPath],
) -> JSONValue:
    if isinstance(value, dict):
        return {
            key: _rebuild(child, (*path, key), substitutions, applied)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [
            _rebuild(item, (*path, index), substitutions, applied)
            for index, item in enumerate(value)
        ]
    if isinstance(value, str):
        if path in substitutions:
            applied.add(path)
            return substitutions[path]
        if path and path[-1] == _ARGUMENTS_KEY:
            parsed = _try_parse_json_container(value)
            if parsed is not None and _has_substitution_beneath(path, substitutions):
                rebuilt = _rebuild(parsed, path, substitutions, applied)
                return json.dumps(rebuilt, ensure_ascii=False)
        return value
    return value


def _try_parse_json_container(value: str) -> dict[str, JSONValue] | list[JSONValue] | None:
    """Parse `value` as JSON if — and only if — it decodes to an object
    or array. `None` if `value` isn't valid JSON at all, or is valid
    JSON but decodes to a scalar (a JSON-encoded string/number/bool):
    only object/array JSON can contain further string leaves worth
    walking into, and a model emitting malformed `arguments` is a real,
    non-exceptional occurrence this function must not raise on — see
    `walk()`'s and `rebuild()`'s shared use of this as a soft fallback
    to opaque-leaf treatment, never an error.
    """
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, (dict, list)):
        return parsed
    return None


def _has_substitution_beneath(path: FieldPath, substitutions: Mapping[FieldPath, str]) -> bool:
    """True iff some substitution's path has `path` as a strict prefix —
    i.e. targets something *inside* the JSON-string field at `path`,
    not the field itself (an exact-path match is handled separately,
    earlier in `_rebuild`, and never reaches this check)."""
    return any(
        len(candidate) > len(path) and candidate[: len(path)] == path for candidate in substitutions
    )
