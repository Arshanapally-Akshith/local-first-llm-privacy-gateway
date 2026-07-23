"""Regression test for the Phase 7 failure-path audit finding:
`DetectionError`, `RehydrationError`, and `NameListExhaustedError` had
no registered `app/main.py` exception handler and fell through to
Starlette's bare, unstructured default 500 — no `{"error": ...}` body,
no distinguishing status code, indistinguishable from an unrelated
crash.

Fixed by `app/main.py`'s `@app.exception_handler(GatewayError)`
catch-all. This test reproduces Starlette's own handler-resolution
lookup (walk `type(exc).__mro__`, return the handler for the first
registered class found) to prove each of the three previously-uncovered
types now resolves to a real handler — and specifically the shared
catch-all, not three separately registered ones, which would itself be
the duplicated-handler pattern this audit exists to prevent.
"""

import pytest

from app.main import app
from src.core.exceptions import (
    DetectionError,
    GatewayError,
    NameListExhaustedError,
    RehydrationError,
)


def _resolves_to_a_registered_handler(exc_type: type[BaseException]) -> bool:
    return any(cls in app.exception_handlers for cls in exc_type.__mro__)


@pytest.mark.parametrize("exc_type", [DetectionError, RehydrationError, NameListExhaustedError])
def test_previously_unhandled_gatewayerror_subclass_now_resolves_to_a_handler(
    exc_type: type[GatewayError],
) -> None:
    assert _resolves_to_a_registered_handler(exc_type)


def test_the_resolved_handler_is_the_shared_catch_all_not_three_new_dedicated_ones() -> None:
    for exc_type in (DetectionError, RehydrationError, NameListExhaustedError):
        assert exc_type not in app.exception_handlers
    assert GatewayError in app.exception_handlers
