"""Shared test setup.

Provides synthetic (non-secret) values for the configuration fields that
have no default — FPE_KEY, SESSION_TTL, FAIL_MODE, UPSTREAM_BASE_URL —
before any test module is collected. app/main.py constructs Settings at
import time, so these must exist before the *first* import of app.main
in this process, not inside a fixture that runs later. Using
`setdefault` means a developer's real `.env` (if present) is never
overridden.

These are placeholder strings for satisfying required-field validation
in tests, not secrets — the same reasoning that lets `.env.example`
itself be committed (CLAUDE.md, "Secrets only in .env"). The
UPSTREAM_BASE_URL placeholder is never actually dialled by most tests
(they use httpx's ASGITransport or TestClient instead) — it only needs
to be a syntactically plausible URL so Settings() validates.
"""

import logging
import os
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest

from src.core.logging import get_gateway_logger
from src.detect.tier2.gliner_model import get_tier2_model
from src.detect.tier2.model import ModelEntityMatch

os.environ.setdefault("FPE_KEY", "test-fpe-key-not-a-real-secret")
os.environ.setdefault("SESSION_TTL", "1800")
os.environ.setdefault("FAIL_MODE", "closed")
os.environ.setdefault("UPSTREAM_BASE_URL", "http://127.0.0.1:8081")


class _NoOpTier2Model:
    """A zero-cost `Tier2Model` stand-in for the FastAPI dependency
    `routes.py::chat_completions` takes on (Phase 4 Task 3,
    `Depends(get_tier2_model)`).

    Without this override, every integration test that POSTs to
    `/v1/chat/completions` through the real `app` — none of which are
    marked `real_model` or have anything to do with Tier-2 detection —
    would trigger FastAPI resolving the *real* `get_tier2_model()`
    dependency at request time and loading actual GLiNER weights
    (multi-second, ~1.5GB+), defeating `pytest.ini`'s entire
    `-m "not real_model"` split. `tests/integration/test_tier2_real_model.py`
    never goes through this override at all — it constructs
    `GLiNERTier2Model`/calls `get_tier2_model()` directly, bypassing
    FastAPI's dependency system entirely, so this fixture never shadows
    it.
    """

    def find_entities(self, text: str) -> list[ModelEntityMatch]:
        return []


@pytest.fixture(autouse=True)
def _no_real_tier2_model_over_http() -> Iterator[None]:
    from app.main import app

    app.dependency_overrides[get_tier2_model] = _NoOpTier2Model
    yield
    app.dependency_overrides.pop(get_tier2_model, None)


class _CollectingHandler(logging.Handler):
    """Collects emitted LogRecords for direct inspection."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture()
def captured_records() -> Iterator[list[logging.LogRecord]]:
    """Capture records emitted on the gateway logger directly.

    Deliberately does not use pytest's `caplog`: caplog's capturing
    handler is attached to the *root* logger, and relies on propagation
    to reach it. `configure_logging()` (invoked at `app.main` import
    time) sets `propagate = False` on the gateway logger — correctly,
    since gateway records must never reach a handler this module didn't
    attach — which means caplog silently sees nothing once any test in
    the same process has imported `app.main`. Attaching a handler
    directly to the gateway logger is what these tests actually need to
    verify, and it is independent of import order across test files.

    Shared here (not duplicated per test module) since both the logging
    tests and fail_mode's "open logs a WARNING" test need it.
    """
    logger = get_gateway_logger()
    logger.setLevel(logging.INFO)
    handler = _CollectingHandler()
    logger.addHandler(handler)
    try:
        yield handler.records
    finally:
        logger.removeHandler(handler)


class FakeClock:
    """Controllable `Clock` test double (`src/core/clock.py`) — time
    only ever moves when `advance()` is called. This is what makes TTL
    expiry testable deterministically, with no `sleep()` anywhere in
    the suite.

    Shared here, not duplicated per test module, since Phase 3's
    session-store, rehydration, and integration tests all need the same
    controllable clock (mirrors why `captured_records` above is shared
    rather than redefined per file).
    """

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start if start is not None else datetime(2026, 1, 1, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta


@pytest.fixture()
def fake_clock() -> FakeClock:
    return FakeClock()
