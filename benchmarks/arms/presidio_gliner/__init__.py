"""Arm 3 — Presidio + custom recognizers + GLiNER backend (BUILD.md,
Phase 5 ablation arm 3).

Arm 2's five Tier-1 custom recognizers, plus a backend swap: Presidio's
own spaCy-backed `PERSON`/`LOCATION`/`NRP`/`DATE_TIME` recognizer
(`SpacyRecognizer`) is removed and replaced with this project's own
`PERSON`/`ORG`/`ADDRESS` detection — the *exact* Tier-2 model this
project's own cascade uses (`gliner_multi_pii-v1`, Phase 4), not a
different GLiNER checkpoint or Presidio's own separate `gliner` extra.

This is a backend *swap*, not an addition, and that distinction is the
entire point of this arm existing: ARCHITECTURE.md's Technology
Decisions section names why arm 3 exists at all — "Choosing GLiNER also
means part of any delta over Presidio is 'we picked a better model,'
which is exactly why arm 3 exists." That comparison is only clean if the
*same* model choice is held constant between "Presidio + our GLiNER" and
"our own cascade" (arm 4) — using this project's own already-warmed,
already-measured `GLiNERTier2Model` via `get_tier2_model()`, rather than
a second, independently-configured GLiNER integration, is what makes
`arm 3 ≈ arm 4` (if that turns out to be the result) mean "the cascade
buys latency, not accuracy" rather than "we happened to pick two
different models that happened to perform similarly."
"""
