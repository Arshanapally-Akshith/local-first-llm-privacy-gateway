"""Fail-open vs fail-closed dispatch.

ARCHITECTURE.md's position: closed is the defensible default for a
privacy product, because a silent leak is worse than a loud outage —
see docs/DECISIONS.md. `Settings.fail_mode` has no default precisely so
this is a conscious operator choice, never inherited (Configuration
Architecture, "No silent security defaults").

Nothing in Phase 1 can actually fail in the way FAIL_MODE is meant to
guard — a detector call. Tier 1 arrives in Phase 2, Tier 2 in Phase 4.
This module exists now because BUILD.md's Phase 1 DoD names it
explicitly, and is proven here with tests that stand in for a real
guarded stage; it is consumed for real once one exists.

Why this lives in core, not pipeline: ARCHITECTURE.md's own failure
taxonomy puts the real call site *below* pipeline — Tier 2's failure
modes say "Model unavailable → FAIL_MODE," a detector-level concern, not
an orchestration one. CLAUDE.md files FAIL_MODE under Security Rules
("Fail-mode is explicit and configured, never implicit"), alongside "no
PII in logs" and "no persistence" — the same class of system-wide
invariant as the logger and the exception hierarchy, not a pipeline
implementation detail. Concretely: CLAUDE.md's layering is
one-directional (proxy -> pipeline -> detect/surrogate/session -> core,
lower layers never import upward). If this lived in `pipeline`, the
moment `detect/tier2/` needs it, something breaks — an upward import
across the frozen boundary, an unnecessary pipeline pass-through, or a
second implementation inside `detect/` (violating "no duplicated
logic"). `core` is the one layer every other layer can already reach
without exception, regardless of which layer turns out to be the real
caller.
"""

from typing import Literal

from src.core.exceptions import GatewayError
from src.core.logging import get_gateway_logger, log_event
from src.core.types import CorrelationId

FailMode = Literal["open", "closed"]


class FailClosedError(GatewayError):
    """Raised when a guarded stage failed under FAIL_MODE=closed.

    The proxy layer, not this module, maps this to a 503 — core must
    not depend on the proxy layer or know about HTTP (CLAUDE.md,
    Modular architecture: "Domain modules never import the proxy
    layer").
    """


def resolve_failure(
    fail_mode: FailMode,
    event: str,
    correlation_id: CorrelationId,
    cause: Exception,
) -> None:
    """Apply FAIL_MODE to a stage that has already failed.

    Callers catch the *specific* exception their stage can raise, then
    call this to decide what happens next. This function does no
    catching itself — which exceptions a stage can raise stays the call
    site's decision, not this module's (CLAUDE.md: "Catch the narrowest
    type you can name").

    `open`: logs at WARNING that a failure was swallowed, then returns
    — the caller proceeds with its own fallback. Silently proceeding
    with no trace at all would be fail-open with extra steps; logging it
    is what keeps "open" an audited choice rather than an invisible one.

    `closed`: raises FailClosedError, chained `from cause`, and does not
    log separately — the raised exception is itself the loud signal.

    Args:
        fail_mode: the configured behaviour.
        event: short, code-authored event name for the log line under
            `open` (e.g. "detection.tier2_failed") — same constraint as
            log_event()'s `event` parameter: never text derived from
            request content.
        correlation_id: threaded through to the log line.
        cause: the exception the guarded stage raised. Never rendered by
            its string content, only by its type name — a stage's
            exception message is not this module's to assume is safe.

    Raises:
        FailClosedError: under fail_mode="closed".
    """
    if fail_mode == "closed":
        raise FailClosedError(
            f"{event} failed under FAIL_MODE=closed: {type(cause).__name__}"
        ) from cause
    log_event(get_gateway_logger(), event, correlation_id=correlation_id)
