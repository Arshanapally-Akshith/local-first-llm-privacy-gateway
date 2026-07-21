"""The rehydration-fidelity harness (BUILD.md, Phase 3): measures, not
fixes, what fraction of name surrogates come back from a model in a
form the conservative, exact-match rehydration engine
(`src/pipeline/rehydrate.py`) can actually resolve.

Lives at the repo root, alongside `benchmarks/` and `adversarial/`
(Phase 5 and Phase 6's own first-class measurement artifacts) rather
than under `src/` or `scripts/`: this is a real, committed evaluation
deliverable in the same spirit as those two, not dev-only tooling and
not gateway runtime code — see `docs/DECISIONS.md` for the placement
decision. Never imported by `src/`.
"""
