"""Arm 4 — this project's own cascade (BUILD.md, Phase 5 ablation arm
4): the last of the four arms, and the one every other arm exists to be
compared against.

Calls `src/detect/cascade.py::detect()` directly — the same function
the live gateway's `sanitize()` pipeline calls on the request path —
not the full `sanitize()`/HTTP round trip. This is a deliberate,
narrower scope than "run examples through the real proxy": BUILD.md's
Phase 5 benchmark measures *detection* (P/R/F1 against gold spans),
never substitution quality, and `sanitize()` would fail outright on any
UPI or email example (`SurrogateDomainError` — no surrogate mechanism
is registered for those two types yet, `docs/LIMITATIONS.md`) despite
`detect()` finding them correctly, since detection and surrogate
generation are separate stages and only the latter has this gap.
Calling `detect()` directly measures exactly what this benchmark needs
and sidesteps a real, disclosed, unrelated limitation rather than
working around it silently.

Uses the exact same GLiNER model (`get_tier2_model()`) as arm 3, for the
same reason arm 3 does: ARCHITECTURE.md's ablation only isolates
"does the cascade help, beyond the model swap" cleanly if the model
choice is held constant between "Presidio + our GLiNER" (arm 3) and
"our own cascade" (this arm).
"""

from datetime import datetime, timezone
from typing import Final

from src.core.fail_mode import FailMode
from src.core.types import CorrelationId, SessionId
from src.detect.cascade import detect
from src.detect.tier2.gliner_model import get_tier2_model
from src.session.session import Session

from benchmarks.arms.arm import Prediction

_CORRELATION_ID: Final[CorrelationId] = CorrelationId("benchmark-arm-ours")
_FAIL_MODE: Final[FailMode] = "closed"
"""Deliberately hardcoded, not read from `.env`/`get_fail_mode()`: a
benchmark run must fail loudly on a detector error, not silently record
a degraded recall number for whichever examples happened to hit it —
"closed" makes any Tier-2 failure during a benchmark run an immediate,
visible crash rather than an invisible dip in arm 4's own numbers that
would look like a genuine detection miss. This is independent of
whatever `FAIL_MODE` the live gateway happens to be configured with — a
benchmark run and a running gateway process have different correctness
requirements for what "a detector failed" should mean."""


class OurCascadeArm:
    """Wraps `cascade.detect()` with a fixed, never-written-to
    `Session` and the shared, real Tier-2 model.

    The `Session` is real, not a mock, but is never mutated:
    `detect()` only ever *reads* session state
    (`session.lookup_surrogate()`, for ingress-surrogate recognition) —
    writing to a session (`allocate_or_lookup_name()`,
    `record_surrogate()`) is `pipeline/sanitize.py`'s job, not
    `detect()`'s (see `cascade.py`'s own module docstring on layering).
    One shared, empty `Session` across every `predict()` call is
    therefore behaviourally identical to constructing a fresh one per
    call, and avoids ~thousands of session-object constructions (one
    per benchmark example) for no observable difference.
    """

    def __init__(self) -> None:
        self._tier2_model = get_tier2_model()
        self._session = Session(
            SessionId("benchmark-arm-ours-session"), created_at=datetime.now(timezone.utc)
        )

    def predict(self, text: str) -> list[Prediction]:
        resolved_spans = detect(
            text,
            self._session,
            self._tier2_model,
            _FAIL_MODE,
            correlation_id=_CORRELATION_ID,
        )
        return [
            Prediction(
                start=resolved.span.start,
                end=resolved.span.end,
                entity_type=resolved.span.entity_type,
            )
            for resolved in resolved_spans
        ]
