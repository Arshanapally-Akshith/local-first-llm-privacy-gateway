"""The Phase 5 benchmark — BUILD.md: "This is the project. Not a
chapter of it."

Lives outside `src/` deliberately: it is a consumer of the gateway's
detection code (`src/detect`), not a layer other gateway code depends
on — the same reason `rehydration_fidelity/` sits at the repository
root rather than under `src/`. See `ARCHITECTURE.md`, Benchmark
Architecture, for the full generation -> arms -> scoring -> artifact
pipeline this package and its siblings (`arms/`, `configs/`, `runner/`,
`results/`, added in later Phase 5 tasks) implement.
"""
