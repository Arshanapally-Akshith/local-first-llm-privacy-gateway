"""Session-scoped, in-memory, TTL-bounded state — the one piece of
mutable state the frozen architecture permits (ARCHITECTURE.md,
Surrogate Architecture: structured entities need no map; names do).

A sibling of `detect/` and `surrogate/` beneath `pipeline/`
(ARCHITECTURE.md's layering diagram). Imports only from `core`; never
imports `proxy` or `pipeline`.
"""
