"""The dataset generator's fixed seed.

`DEFAULT_DATASET_SEED`'s value carries no meaning beyond determinism —
it is not derived from anything, it is simply fixed once so this
module's output never changes unless the generation *code* changes
(mirroring `rehydration_fidelity/runner/run.py::_ALLOCATION_SEED`'s own
documented reasoning, applied here to the benchmark dataset instead of
the rehydration-fidelity harness). Changing this constant regenerates a
different — but equally valid — dataset; it must never be changed
casually, since doing so invalidates any benchmark result already
measured against the previously-generated file (BUILD.md's Phase 5
gate: delete the numbers, run `make bench`, get them back identical —
which requires the dataset itself to be stable across runs, not just
the scoring).
"""

from typing import Final

DEFAULT_DATASET_SEED: Final[int] = 20260722
"""Guess — this task's date, used only as a memorable, arbitrary
constant. No significance beyond that; documented so a future reader
does not go looking for meaning that was never there."""
