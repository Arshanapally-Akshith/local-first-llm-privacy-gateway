"""Proves the PII-safe logger cannot emit plaintext entity values.

This is a security control, not a convenience (CLAUDE.md, Testing
Philosophy: "Test the logger"). Each test targets a distinct way
plaintext could otherwise leak: through an unsanctioned keyword, through
an unbounded entity_type string, or through a raw logger call that
bypasses log_event() entirely.
"""

import json
import logging

import pytest

from src.core.logging import (
    PiiSafeFormatter,
    configure_logging,
    get_gateway_logger,
    log_event,
    redact_safe,
)


def test_redact_safe_returns_only_typed_fields() -> None:
    redacted = redact_safe(
        entity_type="PAN", span_start=10, span_end=20, tier=1, surrogate="ABCDE1234F"
    )

    assert redacted == {
        "entity_type": "PAN",
        "span_start": 10,
        "span_end": 20,
        "tier": 1,
        "surrogate": "ABCDE1234F",
    }


def test_redact_safe_rejects_unexpected_keyword_argument() -> None:
    """There is no parameter for a raw value — passing one is a TypeError,
    not a validation error, because the signature itself has no slot for
    it."""
    with pytest.raises(TypeError):
        redact_safe(  # type: ignore[call-arg]
            entity_type="PAN",
            span_start=10,
            span_end=20,
            tier=1,
            surrogate="ABCDE1234F",
            raw_value="the real PAN would go here",
        )


def test_redact_safe_rejects_unknown_entity_type() -> None:
    with pytest.raises(ValueError, match="unknown entity_type"):
        redact_safe(
            entity_type="RAMESH_KUMAR",  # type: ignore[arg-type]
            span_start=0,
            span_end=5,
            tier=1,
            surrogate="x",
        )


def test_redact_safe_rejects_unknown_tier() -> None:
    with pytest.raises(ValueError, match="unknown tier"):
        redact_safe(entity_type="PAN", span_start=0, span_end=5, tier=3, surrogate="x")  # type: ignore[arg-type]


@pytest.mark.parametrize("span_start,span_end", [(-1, 5), (10, 5)])
def test_redact_safe_rejects_invalid_span(span_start: int, span_end: int) -> None:
    with pytest.raises(ValueError, match="invalid span"):
        redact_safe(
            entity_type="PAN", span_start=span_start, span_end=span_end, tier=1, surrogate="x"
        )


def test_log_event_output_contains_only_whitelisted_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger = get_gateway_logger()
    logger.setLevel(logging.INFO)
    redacted = redact_safe(
        entity_type="AADHAAR", span_start=5, span_end=17, tier=1, surrogate="999912345678"
    )

    with caplog.at_level(logging.INFO, logger="gateway"):
        log_event(
            logger,
            "detection.span_resolved",
            correlation_id="corr-1",
            session_id="sess-1",
            redacted=redacted,
            latency_ms=1.5,
        )

    assert len(caplog.records) == 1
    formatted = json.loads(PiiSafeFormatter().format(caplog.records[0]))

    expected_keys = {
        "timestamp",
        "level",
        "logger",
        "event",
        "correlation_id",
        "session_id",
        "entity_type",
        "span_start",
        "span_end",
        "tier",
        "surrogate",
        "latency_ms",
    }
    assert set(formatted.keys()) == expected_keys
    assert formatted["event"] == "detection.span_resolved"
    assert formatted["correlation_id"] == "corr-1"
    assert formatted["session_id"] == "sess-1"
    assert formatted["entity_type"] == "AADHAAR"
    assert formatted["span_start"] == 5
    assert formatted["span_end"] == 17
    assert formatted["tier"] == 1
    assert formatted["surrogate"] == "999912345678"
    assert formatted["latency_ms"] == 1.5


def test_formatter_never_emits_a_raw_bypass_call_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A call that bypasses log_event() entirely — e.g. a future bug that
    calls logger.info(f"...") directly — must not leak its message. This
    is the defense-in-depth layer: it holds even when the sanctioned API
    (log_event/redact_safe) is bypassed."""
    logger = get_gateway_logger()
    logger.setLevel(logging.INFO)
    stand_in_for_a_real_pan = "ABCDE1234F"

    with caplog.at_level(logging.INFO, logger="gateway"):
        logger.info("plaintext leak attempt: %s", stand_in_for_a_real_pan)

    assert len(caplog.records) == 1
    formatted_str = PiiSafeFormatter().format(caplog.records[0])

    assert stand_in_for_a_real_pan not in formatted_str
    assert "plaintext leak attempt" not in formatted_str
    assert "leak" not in formatted_str


def test_formatter_drops_unknown_extra_fields_instead_of_raising(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Simulates a hypothetical bug elsewhere attaching a non-whitelisted
    field directly. The formatter must drop it silently, not crash — a
    logging control that can take down the process on unexpected input
    is itself an availability risk."""
    logger = get_gateway_logger()
    logger.setLevel(logging.INFO)

    with caplog.at_level(logging.INFO, logger="gateway"):
        logger.info("", extra={"real_entity_value": "Priya Sharma"})

    assert len(caplog.records) == 1
    formatted_str = PiiSafeFormatter().format(caplog.records[0])

    assert "Priya Sharma" not in formatted_str
    assert "real_entity_value" not in formatted_str
    json.loads(formatted_str)  # still valid, well-formed JSON


def test_configure_logging_is_idempotent() -> None:
    configure_logging("INFO")
    configure_logging("INFO")

    logger = get_gateway_logger()
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0].formatter, PiiSafeFormatter)
