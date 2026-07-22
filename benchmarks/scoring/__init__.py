"""The scorer: implements the exact-span, exact-type matching criterion
fixed in `docs/DECISIONS.md` (2026-07-22, "Phase 5 Task 1") before any
arm existed.

That entry deferred two things to "the scorer task": the canonical
cross-arm entity-type mapping, and the one-to-one assignment algorithm
for duplicate/ambiguous matches. The first turned out to already be
solved by the time this task started — every arm (Tasks 4-6) already
translates its own output into this project's `EntityType` vocabulary
before returning a `Prediction` (`benchmarks/arms/presidio_results.py`
for the Presidio-backed arms; `Tier2Detector`/Tier-1 `Detector`s
directly for arm 4) — so this module never sees a raw Presidio label or
a raw GLiNER label, only `EntityType` on both sides of every comparison.
Only the second (`score.py::score_example()`) is this task's own work.
"""
