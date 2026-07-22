"""Auto-discovery of bypass-class case modules — the Staff Engineer
review's required change #2: "avoid maintaining a growing import list
inside the runner... adding a new bypass class later requires only
adding a new case module."

Every real bypass-class module (`spaced_digits.py`, `homoglyphs.py`,
...) exposes a module-level `build_cases() -> list[AdversarialCase]`.
Infrastructure modules (`case_types`, `verify`, `carrier`, this module
itself) do not, and are skipped for exactly that reason — there is no
separate allowlist of "infrastructure module names" to keep in sync
with reality; the only signal this function looks for is the presence
of `build_cases`, mirroring the same open/closed principle
`src/detect/registry.py` already applies to detectors ("adding an
entity type is a new detector registered in a registry, not an `if`
branch in the pipeline" — CLAUDE.md).
"""

import importlib
import pkgutil
from collections.abc import Iterable
from typing import Final

import adversarial.cases as cases_package
from adversarial.cases.case_types import AdversarialCase

_BUILD_CASES_ATTR: Final[str] = "build_cases"


def _assert_unique_case_ids(cases: Iterable[AdversarialCase]) -> None:
    """Raise loudly on the first case whose `case_id` repeats one
    already seen. Pulled out as its own function so this invariant is
    directly unit-testable without mocking `pkgutil`/`importlib`.

    Raises:
        ValueError: two cases (from the same module or different ones)
            share a `case_id` — a real authoring bug (case ids scope
            per-case verification and per-class reporting; a silent
            collision would make one case's result overwrite another's
            in the aggregated report), caught here rather than
            discovered later as an inexplicably-missing case.
    """
    seen_case_ids: set[str] = set()
    for case in cases:
        if case.case_id in seen_case_ids:
            raise ValueError(
                f"duplicate adversarial case_id {case.case_id!r} - case ids must be "
                "globally unique across every bypass-class module"
            )
        seen_case_ids.add(case.case_id)


def discover_cases() -> list[AdversarialCase]:
    """Import every module under `adversarial.cases` that defines
    `build_cases()`, call it, and return every case it produced, sorted
    by `case_id`.

    `pkgutil.iter_modules()` does not guarantee any particular
    iteration order — it reflects whatever order the underlying
    filesystem finder happens to enumerate directory entries in, which
    is not the same across operating systems (a real, observed
    difference between Windows and Linux directory listing order) or
    guaranteed stable across Python versions. Two independent
    determinism guards are applied for this reason, not one: modules
    are imported in sorted-by-name order (so import side effects, and
    any future module-level logging, happen in a fixed sequence too),
    and the final case list is sorted by `case_id` regardless of which
    module or what order produced it — the second guard is what
    actually makes `adversarial/results/latest.json`'s `"cases"` array
    (a JSON list, which `json.dumps(..., sort_keys=True)` does not
    reorder) byte-reproducible across machines and CI runs.

    Raises:
        ValueError: see `_assert_unique_case_ids()`.
    """
    all_cases: list[AdversarialCase] = []
    for module_info in sorted(pkgutil.iter_modules(cases_package.__path__), key=lambda m: m.name):
        module = importlib.import_module(f"adversarial.cases.{module_info.name}")
        build_cases = getattr(module, _BUILD_CASES_ATTR, None)
        if build_cases is None:
            continue
        all_cases.extend(build_cases())
    _assert_unique_case_ids(all_cases)
    return sorted(all_cases, key=lambda case: case.case_id)
