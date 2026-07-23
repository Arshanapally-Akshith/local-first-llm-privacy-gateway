"""PII-safe structured logging.

Every log line in this system goes through `log_event()`, which has no
parameter for a free-text message or an arbitrary value — only a fixed
set of typed, structured fields. `redact_safe()` is the sanctioned way
to turn a detected entity into something loggable: it accepts entity
type, span offsets, tier, and surrogate, and nothing else, so there is
no parameter through which a real detected value could be passed.

`PiiSafeFormatter` is the second, independent layer: it never reads a
LogRecord's free-text message at all, and renders only a fixed field
allowlist. This means even a call that bypasses `log_event()` entirely
(a raw `logger.info("...")` on the gateway logger) cannot get its
message content into the rendered output — the guarantee holds at the
formatter, not just at the API surface that is supposed to be the only
caller.
"""

import json
import logging
from typing import Final, TypedDict

from src.core.types import ENTITY_TYPES, TIERS, EntityType, Tier

_LOGGER_NAME: Final[str] = "gateway"

_ALLOWED_FIELDS: Final[tuple[str, ...]] = (
    "event",
    "correlation_id",
    "session_id",
    "entity_type",
    "span_start",
    "span_end",
    "tier",
    "surrogate",
    "latency_ms",
    "timestamp_ms",
)
"""Every field name the formatter will ever render. Anything attached to
a LogRecord under a different name — including via a raw, undisciplined
logger call — is silently dropped by PiiSafeFormatter, never raised on.
See PiiSafeFormatter's docstring for why silent-drop is the correct
failure mode for this specific control."""


class RedactedEntity(TypedDict):
    """A detected entity in the only shape that is safe to log."""

    entity_type: EntityType
    span_start: int
    span_end: int
    tier: Tier
    surrogate: str


def redact_safe(
    *,
    entity_type: EntityType,
    span_start: int,
    span_end: int,
    tier: Tier,
    surrogate: str,
) -> RedactedEntity:
    """Build the only log-safe representation of a detected entity.

    Refuses plaintext structurally, not by convention: the signature has
    no parameter that could carry the real detected value, so there is
    no argument position through which one could be passed. `surrogate`
    is accepted and logged because it is fake by construction — see
    ARCHITECTURE.md, Logging Architecture, "Why the surrogate is safe to
    log and the real value is not." This function cannot verify that
    claim about a given string; it is a call-site contract, not
    something inferable from the string alone.

    Raises:
        ValueError: entity_type or tier is outside the closed
            vocabulary, or the span is malformed (negative offset, or
            end before start). A malformed span here means a detector
            emitted something that cannot correspond to a real
            substring — that is exceptional, not expected, and must
            raise rather than log something misleading.
    """
    if entity_type not in ENTITY_TYPES:
        raise ValueError(
            f"unknown entity_type {entity_type!r}; must be one of {sorted(ENTITY_TYPES)}"
        )
    if tier not in TIERS:
        raise ValueError(f"unknown tier {tier!r}; must be one of {sorted(TIERS)}")
    if span_start < 0 or span_end < span_start:
        raise ValueError(f"invalid span ({span_start}, {span_end}) for entity_type={entity_type}")
    return RedactedEntity(
        entity_type=entity_type,
        span_start=span_start,
        span_end=span_end,
        tier=tier,
        surrogate=surrogate,
    )


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    correlation_id: str,
    session_id: str | None = None,
    redacted: RedactedEntity | None = None,
    latency_ms: float | None = None,
    timestamp_ms: float | None = None,
) -> None:
    """Emit one structured log line through the PII-safe formatter.

    `event` is a short, code-authored identifier (e.g.
    "detection.span_resolved"), never text derived from request content —
    it is the only string field here with no closed vocabulary, so that
    discipline is load-bearing and worth stating explicitly. Every other
    field is either typed/bounded (`redacted`) or opaque
    (`correlation_id`, `session_id`).

    `timestamp_ms` (epoch milliseconds, from the caller's own injected
    `Clock` — never a bare `time.time()` inline) exists for the Phase 7
    latency harness: `src/proxy/routes.py`'s `latency.upstream_first_chunk`
    and `latency.window_first_release` events use it so the harness,
    reading these two absolute timestamps back out of a captured log
    file, can compute the sliding window's TTFT tax as a plain
    subtraction — without needing to also parse the log line's own
    `timestamp` field's default (locale/format-dependent) string
    rendering. Unrelated to `latency_ms`, which records an already-
    computed *duration* (e.g. `startup.tier2_model_warmed`); this field
    is a point in time.

    The underlying stdlib call passes `event` via `extra`, not as the
    LogRecord message, and with an empty message string — so even this
    sanctioned call path never puts free text into `record.msg`.
    """
    fields: dict[str, object] = {"event": event, "correlation_id": correlation_id}
    if session_id is not None:
        fields["session_id"] = session_id
    if redacted is not None:
        fields.update(redacted)
    if latency_ms is not None:
        fields["latency_ms"] = latency_ms
    if timestamp_ms is not None:
        fields["timestamp_ms"] = timestamp_ms
    logger.info("", extra=fields)


class PiiSafeFormatter(logging.Formatter):
    """Structured JSON formatter that can only emit a fixed field allowlist.

    Deliberately never calls `record.getMessage()` — the free-text
    message every stdlib logging call accepts as its first argument —
    so a call that bypasses `log_event()` and invokes `logger.info(...)`
    directly on the gateway logger cannot get its message content into
    the rendered output. Every other attribute on the record is rendered
    only if its name is in `_ALLOWED_FIELDS`; anything else is silently
    ignored rather than raised on, so a misbehaving or third-party log
    call degrades to a sparse structured line instead of crashing the
    process. A security control whose job is containment should not
    itself become an availability risk.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
        }
        for field in _ALLOWED_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, sort_keys=True)


def configure_logging(level: str) -> None:
    """Attach the PII-safe formatter to the gateway logger.

    Idempotent: clears any handlers already attached before adding a
    fresh one, so calling this more than once (under `--reload`, or
    repeatedly across tests) never accumulates duplicate handlers and
    never falls back to logging's own default formatter, which has no
    restriction on what it renders. `propagate = False` keeps gateway
    log records off the root logger, so nothing upstream of this module
    can attach an unsafe formatter to them.
    """
    logger = logging.getLogger(_LOGGER_NAME)
    logger.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(PiiSafeFormatter())
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False


def get_gateway_logger() -> logging.Logger:
    """Return the gateway's PII-safe logger.

    Pass this into `log_event()`. Calling `.info()` / `.warning()` etc.
    on it directly with a free-text message will not raise, but the
    message will not appear in the rendered output either — see
    PiiSafeFormatter. `log_event()` is the intended and only sanctioned
    entry point.
    """
    return logging.getLogger(_LOGGER_NAME)
