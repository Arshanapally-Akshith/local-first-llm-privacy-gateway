"""Sanitize — the request-path orchestrator: real values -> surrogates
(CLAUDE.md vocabulary: "sanitize — request path, real -> surrogate").

Composes the pieces earlier tasks built in isolation, without
re-implementing any of them (CLAUDE.md: "No duplicated logic"): the
field walker (every text-bearing field, plus rebuild), the detection
cascade (Tier-1 spans, overlap-resolved), and the surrogate engine (FF1
encrypt). This module owns none of that logic — only the order to call
it in.

A request body is either fully sanitized or never forwarded.
`field_walker.rebuild()` is called exactly once, after every region has
been walked and every span in every region has been substituted. If
any span cannot be given a surrogate (`SurrogateDomainError` — true
today for UPI and email, which have no registered domain until Phase
3's session map exists), the exception propagates out of `sanitize()`
before `rebuild()` ever runs. There is no code path that forwards a
partially-sanitized body.
"""

from src.core.logging import get_gateway_logger, log_event, redact_safe
from src.core.types import CorrelationId
from src.detect.cascade import detect
from src.pipeline.field_walker import FieldPath, JSONValue, TextRegion, rebuild, walk
from src.surrogate import engine
from src.surrogate.key_provider import KeyProvider


def sanitize(
    body: dict[str, JSONValue],
    key_provider: KeyProvider,
    *,
    correlation_id: CorrelationId,
) -> dict[str, JSONValue]:
    """Return a new body with every detected Tier-1 entity replaced by
    its surrogate, at every text-bearing field `field_walker.walk()`
    finds — system prompt, every message role, tool/function
    definitions, tool-result messages, function-call arguments, `name`
    fields (see `field_walker.py`'s own docstring for the traversal
    rules). Does not mutate `body`.

    Raises:
        SurrogateDomainError: a detected span's entity type has no
            registered surrogate domain (UPI, email) — propagates
            before any substitution is applied to the returned body,
            per the module docstring.
    """
    substitutions: dict[FieldPath, str] = {}
    for region in walk(body):
        new_text = _sanitize_region(region, key_provider, correlation_id)
        if new_text is not None:
            substitutions[region.path] = new_text

    result = rebuild(body, substitutions)
    sanitized = result.body
    assert isinstance(sanitized, dict), "rebuild() preserves a dict body's top-level type"
    return sanitized


def _sanitize_region(
    region: TextRegion, key_provider: KeyProvider, correlation_id: CorrelationId
) -> str | None:
    """Return `region.text` with every detected span replaced by its
    surrogate, or `None` if nothing was detected — so the caller can
    skip an unnecessary substitution entry for a region that is
    unchanged.

    Spans are applied start-descending so each splice only ever touches
    text to the right of positions already processed. This also holds
    for same-length surrogates (guaranteed by every FF1 domain — Tier-1
    substitution is always format-preserving) without depending on
    that guarantee to be safe for out-of-order or overlapping spans,
    since `detect()` already returns a non-overlapping set.
    """
    spans = detect(region.text)
    if not spans:
        return None

    logger = get_gateway_logger()
    new_text = region.text
    for span in sorted(spans, key=lambda s: s.start, reverse=True):
        value = region.text[span.start : span.end]
        surrogate = engine.encrypt(span.entity_type, value, key_provider)
        new_text = new_text[: span.start] + surrogate + new_text[span.end :]
        log_event(
            logger,
            "pipeline.span_sanitized",
            correlation_id=correlation_id,
            redacted=redact_safe(
                entity_type=span.entity_type,
                span_start=span.start,
                span_end=span.end,
                tier=span.tier,
                surrogate=surrogate,
            ),
        )
    return new_text
