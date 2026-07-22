"""The four Phase 5 ablation arms (BUILD.md, ARCHITECTURE.md's Benchmark
Architecture): stock Presidio, Presidio + custom recognizers, Presidio +
custom recognizers + GLiNER backend, and this project's own cascade.

Only arm 1 (`presidio_stock.py`) and arm 2 (`presidio_custom/`) exist so
far (Phase 5 Task 4). Arms 3 and 4 are later tasks, not started.

Every arm shares one shape (`arm.py::Arm`): given raw text, return every
predicted entity as a `Prediction` in this project's own `EntityType`
vocabulary — never a baseline's raw label. This is what lets a future
scorer compare any arm's output against `benchmarks/generate`'s gold
`GoldEntity` values without knowing anything about which baseline
produced them.
"""
