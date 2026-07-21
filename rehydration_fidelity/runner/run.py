"""The rehydration-fidelity harness entrypoint (BUILD.md, Phase 3):
allocates a name surrogate for each of `taxonomy.SAMPLE_REAL_NAMES`,
runs every `taxonomy.TAXONOMY` category's transform over each surrogate,
rehydrates the result through the real `src/pipeline/rehydrate.py`, and
records — per category — what fraction round-tripped to the exact real
value. Writes the result to `rehydration_fidelity/results/latest.json`,
stamped with the commit that produced it (CLAUDE.md: "current metrics
with the commit hash that produced them").

This measures; it does not assert. There is no pass/fail here — a
category landing at 0% is exactly as valid an outcome as one at 100%,
and both are reported identically (BUILD.md: "Measure, don't fix").

Run with:
    python -m rehydration_fidelity.runner.run
"""

import json
import logging
import random
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, TypedDict

from src.core.types import CorrelationId, SessionId
from src.pipeline.rehydrate import rehydrate
from src.session.names import DEFAULT_NAME_CANDIDATES
from src.session.session import Session

from rehydration_fidelity.runner.taxonomy import SAMPLE_REAL_NAMES, TAXONOMY, TaxonomyCategory

_logger = logging.getLogger("rehydration_fidelity")
_logger.setLevel(logging.INFO)
_logger.addHandler(logging.StreamHandler())
"""A plain stdlib logger, not the gateway's PII-safe one
(`src/core/logging.py`): that formatter is a security control for the
running gateway process handling real (if sanitized) traffic, and its
fixed field allowlist has no slot for "here is a per-category hit-rate
summary." Nothing this harness logs is real PII regardless — every
sample name here is synthetic (`taxonomy.SAMPLE_REAL_NAMES`) — so the
PII-safety constraint that formatter exists to enforce does not apply
to this runner in the first place."""

_RESULTS_PATH: Final[Path] = Path(__file__).resolve().parent.parent / "results" / "latest.json"
_CORRELATION_ID: Final[CorrelationId] = CorrelationId("rehydration-fidelity-harness")
_ALLOCATION_SEED: Final[int] = 0
"""Fixed, not system entropy: this harness's own numbers must be
reproducible run to run until the code actually changes — the same
"delete and regenerate, get identical output" discipline
ARCHITECTURE.md requires of the Phase 5 benchmark, applied here first.
The specific seed value carries no meaning beyond determinism; which
surrogate string each sample real name happens to land on does not
affect any category's hit rate (every sample is a "First Last" shape
name, and every taxonomy transform operates on that shape uniformly)."""


class _UnusedKeyProvider:
    """`rehydrate()` requires a `KeyProvider`, but every sample this
    harness exercises is a `PERSON` (name-map) entity type, which never
    reaches FF1 decryption. `get_key()` being called at all would mean
    a category somehow produced a structured-entity-shaped match,
    which should be impossible given `taxonomy.TAXONOMY` only ever
    transforms `PERSON` surrogates — raising loudly turns that
    assumption into something that fails fast rather than silently
    returning a meaningless key.
    """

    def get_key(self) -> bytes:
        raise AssertionError(
            "KeyProvider.get_key() was called during the rehydration-fidelity harness; "
            "every sample here is a PERSON entity type and should never reach FF1"
        )


@dataclass(frozen=True, slots=True)
class CategoryResult:
    hits: int
    total: int

    @property
    def hit_rate(self) -> float:
        return self.hits / self.total if self.total else 0.0


class CategorySummary(TypedDict):
    hits: int
    total: int
    hit_rate: float


class FidelityReport(TypedDict):
    commit: str
    sample_size: int
    categories: dict[str, CategorySummary]


def _allocate_surrogates(session: Session, real_names: tuple[str, ...]) -> dict[str, str]:
    rng = random.Random(_ALLOCATION_SEED)
    now = datetime.now(timezone.utc)
    return {
        real_name: session.allocate_or_lookup_name(
            real_name, "PERSON", list(DEFAULT_NAME_CANDIDATES), rng, now
        )
        for real_name in real_names
    }


def _run_category(
    category: TaxonomyCategory,
    real_to_surrogate: dict[str, str],
    session: Session,
    key_provider: _UnusedKeyProvider,
) -> CategoryResult:
    hits = 0
    for real_name, surrogate in real_to_surrogate.items():
        returned_form = category.transform(surrogate)
        carrier_text = f"Noted: {returned_form}."
        rehydrated = rehydrate(carrier_text, session, key_provider, correlation_id=_CORRELATION_ID)
        if real_name in rehydrated:
            hits += 1
    return CategoryResult(hits=hits, total=len(real_to_surrogate))


def build_report() -> FidelityReport:
    """Run every taxonomy category against every sample real name and
    return the report `main()` writes to the artifact.

    Kept separate from `main()` so unit tests can assert on the
    report's structure and on category rates that are guaranteed by
    construction, without touching the filesystem or invoking git.
    """
    session = Session(
        SessionId("rehydration-fidelity-harness-session"), created_at=datetime.now(timezone.utc)
    )
    key_provider = _UnusedKeyProvider()
    real_to_surrogate = _allocate_surrogates(session, SAMPLE_REAL_NAMES)

    results = {
        category.name: _run_category(category, real_to_surrogate, session, key_provider)
        for category in TAXONOMY
    }
    return {
        "commit": _current_commit_hash(),
        "sample_size": len(SAMPLE_REAL_NAMES),
        "categories": {
            name: {"hits": result.hits, "total": result.total, "hit_rate": result.hit_rate}
            for name, result in results.items()
        },
    }


def _current_commit_hash() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).resolve().parent,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return completed.stdout.strip()


def main() -> None:
    report = build_report()
    _RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _RESULTS_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    _logger.info("wrote %s", _RESULTS_PATH)
    for name, category_result in report["categories"].items():
        _logger.info(
            "category=%s hits=%s total=%s hit_rate=%s",
            name,
            category_result["hits"],
            category_result["total"],
            category_result["hit_rate"],
        )


if __name__ == "__main__":
    main()
