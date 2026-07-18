"""Proves FAIL_MODE dispatch: open swallows-and-logs, closed raises.

Uses a plain RuntimeError as a stand-in for a real guarded stage's
failure — no detector exists yet to fail for real (Tier 1 is Phase 2,
Tier 2 is Phase 4). This module is proven now against that stand-in and
consumed for real once a guarded stage exists.
"""

import json
import logging

import pytest

from src.core.fail_mode import FailClosedError, resolve_failure
from src.core.logging import PiiSafeFormatter
from src.core.types import CorrelationId


def test_resolve_failure_open_logs_and_returns(
    captured_records: list[logging.LogRecord],
) -> None:
    cause = RuntimeError("stand-in stage failure")

    resolve_failure("open", "test.stage_failed", CorrelationId("corr-1"), cause)

    assert len(captured_records) == 1
    formatted = json.loads(PiiSafeFormatter().format(captured_records[0]))
    assert formatted["event"] == "test.stage_failed"
    assert formatted["correlation_id"] == "corr-1"


def test_resolve_failure_closed_raises_chained_and_does_not_log(
    captured_records: list[logging.LogRecord],
) -> None:
    cause = RuntimeError("stand-in stage failure")

    with pytest.raises(FailClosedError) as exc_info:
        resolve_failure("closed", "test.stage_failed", CorrelationId("corr-1"), cause)

    assert exc_info.value.__cause__ is cause
    assert len(captured_records) == 0


def test_resolve_failure_closed_message_never_includes_the_causes_text() -> None:
    cause = RuntimeError("a message that must not leak")

    with pytest.raises(FailClosedError) as exc_info:
        resolve_failure("closed", "test.stage_failed", CorrelationId("x"), cause)

    assert "a message that must not leak" not in str(exc_info.value)
    assert "RuntimeError" in str(exc_info.value)
