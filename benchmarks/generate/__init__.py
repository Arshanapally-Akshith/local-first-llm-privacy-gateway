"""Dataset generation — slot-and-inject (BUILD.md, Phase 5).

Carrier sentences with `{ENTITY_TYPE}` slots (`templates.py`) are
authored content, not fetched from a live LLM API at build time: this
project requires no paid API key or network access to run, test, or
benchmark (CLAUDE.md constraint #2), and byte-for-byte reproducible
regeneration (requirement of this task) is incompatible with a live
generation call that could return different phrasing on every run.
BUILD.md's "LLM generates carrier sentences with slots" step is
satisfied by having been performed once, offline, by the assistant
authoring `templates.py`, exactly as `src/session/names.py`'s and
`org_names.py`'s candidate pools were authored rather than fetched.

What *is* generated programmatically, at every run, deterministically,
is the entity values (`entity_values.py`) and their injection into the
templates (`inject.py`) — the step BUILD.md actually requires to be
mechanical: "entities are injected programmatically. Gold offsets are
exact by construction."
"""
