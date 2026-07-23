"""`LatencyWorkload` — one fixed, deterministic request-body shape the
Phase 7 harness sends repeatedly at every concurrency level.

Each workload isolates exactly one cost axis (see `definitions.py`'s
module docstring) — never a combination of two, the same ablation
discipline `benchmarks/arms/` applies to detection accuracy, applied
here to latency instead.
"""

from dataclasses import dataclass

from src.pipeline.field_walker import JSONValue


@dataclass(frozen=True, slots=True)
class LatencyWorkload:
    """One request body, sent byte-identical on every repetition.

    A fixed instance, not a factory function: the content itself is
    part of the methodology (Phase 7 design, "noise minimization" — a
    workload's content must never vary run to run, so any variance
    measured across repetitions is process/scheduling noise, not
    workload noise).
    """

    name: str
    description: str
    request_body: dict[str, JSONValue]

    @property
    def streaming(self) -> bool:
        """Derived from `request_body["stream"]`, never a second,
        independently-set field — two sources of truth for the same
        fact is exactly the duplicated-state CLAUDE.md's "no duplicated
        logic" rule exists to prevent."""
        return bool(self.request_body.get("stream", False))
