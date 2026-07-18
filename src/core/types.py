"""Distinct identifier types.

NewType wrappers so an opaque identifier of one kind cannot be passed
where a different kind is expected without mypy --strict catching it.
NewType adds no runtime validation — it is erased at runtime — so it is
the right tool for genuinely-arbitrary-string identifiers (any string
is a legitimate CorrelationId), and the wrong tool for closed
vocabularies. `EntityType` (src/core/logging.py) uses a runtime-checked
Literal instead, for exactly that reason: entity types are a small
fixed set where a caller passing an arbitrary string is a real bug this
project must catch even outside mypy; correlation ids have no such
fixed set to check against.
"""

from typing import NewType

CorrelationId = NewType("CorrelationId", str)
"""Opaque per-request identifier, assigned once at ingress by the proxy
and threaded through every log line for that request (CLAUDE.md,
Structured logging: "Every request carries a correlation id from
ingress through rehydration"). Generation happens in the proxy route
handler (Phase 1, Task 4); this type exists now because
`fail_mode.resolve_failure()` already needs to accept one.
"""
