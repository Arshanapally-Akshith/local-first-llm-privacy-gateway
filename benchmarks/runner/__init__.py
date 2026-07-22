"""The `make bench` equivalent (BUILD.md, Phase 5): runs all four
ablation arms against the committed dataset, scores each under the
fixed exact-span/exact-type criterion (`docs/DECISIONS.md`,
2026-07-22), and writes a commit-stamped results artifact plus a
regenerable markdown table — `benchmarks/results/`.

Mirrors `rehydration_fidelity/runner/run.py`'s established shape
(`build_report()` separate from `main()` for testability without
filesystem/git access; a plain stdlib logger, not the gateway's
PII-safe one, since nothing here is real PII).
"""
