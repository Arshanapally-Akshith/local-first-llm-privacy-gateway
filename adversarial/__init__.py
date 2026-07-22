"""The adversarial bypass suite (BUILD.md Phase 6; ARCHITECTURE.md's
"Adversarial Evaluation" section — the frozen spec this package
implements).

Unlike `benchmarks/` (Phase 5), which calls `src/detect/cascade.py`
directly to score detection spans, this package runs every case
through the real, running gateway end to end and inspects what the
mock upstream actually received — ARCHITECTURE.md is explicit that
bypasses like split-across-turns "only exist at the system level," so
an in-process detector call cannot exercise them.

See `adversarial/cases/` (one module per bypass class, auto-discovered
— no import list to maintain), `adversarial/runner/` (executes every
case against the live app and renders the report), and
`adversarial/results/` (the committed, commit-stamped artifact).
"""
