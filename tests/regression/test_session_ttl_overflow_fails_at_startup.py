"""Regression test for a Phase 7 configuration-hardening finding: an
absurdly large `SESSION_TTL` passed `Settings()` construction cleanly
(it satisfied `gt=0`, the only constraint that existed on the field),
and only failed with a bare, uncaught `OverflowError` inside
`get_session_store()` (`src/session/store.py`) — which unconditionally
builds `timedelta(seconds=settings.session_ttl)` — on the *first
request*, not at startup. This directly violated this project's own
"fail loud at startup, never at first request" invariant (BUILD.md
Phase 0 DoD; `ARCHITECTURE.md`, Configuration Architecture).

Fixed by `Settings._session_ttl_must_fit_a_timedelta`
(`src/core/config.py`): a value that cannot fit in a `timedelta` now
fails `Settings()` construction itself, with a clean, actionable
`pydantic.ValidationError` instead of a bare `OverflowError` three
layers downstream.
"""

from datetime import timedelta

import pytest
from pydantic import SecretStr, ValidationError

from src.core.config import Settings

_OVERFLOWING_SESSION_TTL = 86_400 * 1_000_000_000  # exceeds timedelta's own max (999,999,999 days)


def test_session_ttl_overflow_is_rejected_at_settings_construction_not_at_first_request() -> None:
    # The exact overflow this construction previously deferred to:
    # confirms the symptom would otherwise reproduce downstream.
    with pytest.raises(OverflowError):
        timedelta(seconds=_OVERFLOWING_SESSION_TTL)

    # Settings() must now refuse this value itself, before any request
    # — and specifically as a clean ValidationError, not the bare
    # OverflowError the line above demonstrates would otherwise occur
    # three layers downstream, inside get_session_store().
    with pytest.raises(ValidationError):
        Settings(
            upstream_base_url="http://127.0.0.1:8081",
            fpe_key=SecretStr("a-strong-operator-secret"),
            session_ttl=_OVERFLOWING_SESSION_TTL,
            fail_mode="closed",
        )
