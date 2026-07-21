"""Sanitize — the request-path orchestrator: real values -> surrogates
(CLAUDE.md vocabulary: "sanitize — request path, real -> surrogate").

Composes the pieces earlier tasks built in isolation, without
re-implementing any of them (CLAUDE.md: "No duplicated logic"): the
field walker (every text-bearing field, plus rebuild), the detection
cascade (Tier-1 + Tier-2 spans, overlap-resolved, ingress-recognised),
the surrogate engine (FF1 encrypt) for fixed-domain entities, and
`Session.allocate_or_lookup_name()` (Phase 4 Task 5) for the three
unbounded-domain, name-map entity types (`PERSON`/`ORG`/`ADDRESS`,
`src/session/candidates.py::NAME_MAP_ENTITY_TYPES`). This module owns
none of that logic — only the order to call it in, which mechanism a
given entity type uses, and the one policy decision that belongs at
orchestration level rather than inside any of those pieces: an
ingress-recognised span is never re-encrypted (Phase 3 architectural
decision: "security policy remains inside pipeline orchestration").

A request body is either fully sanitized or never forwarded.
`field_walker.rebuild()` is called exactly once, after every region has
been walked and every span in every region has been substituted. If
any span cannot be given a surrogate (`SurrogateDomainError` — true
today for UPI and email, which have no registered domain and no
candidate pool), the exception propagates out of `sanitize()` before
`rebuild()` ever runs. There is no code path that forwards a
partially-sanitized body.
"""

import random
from datetime import datetime

from src.core.clock import Clock
from src.core.fail_mode import FailMode
from src.core.logging import get_gateway_logger, log_event, redact_safe
from src.core.types import CorrelationId
from src.detect.cascade import detect
from src.detect.tier2.model import Tier2Model
from src.pipeline.field_walker import FieldPath, JSONValue, TextRegion, rebuild, walk
from src.session.candidates import NAME_MAP_ENTITY_TYPES, get_candidates
from src.session.session import Session
from src.surrogate import engine
from src.surrogate.key_provider import KeyProvider


def sanitize(
    body: dict[str, JSONValue],
    key_provider: KeyProvider,
    session: Session,
    clock: Clock,
    tier2_model: Tier2Model,
    fail_mode: FailMode,
    rng: random.Random,
    *,
    correlation_id: CorrelationId,
) -> dict[str, JSONValue]:
    """Return a new body with every detected Tier-1 and Tier-2 entity
    replaced by its surrogate, at every text-bearing field
    `field_walker.walk()` finds — system prompt, every message role,
    tool/function definitions, tool-result messages, function-call
    arguments, `name` fields (see `field_walker.py`'s own docstring for
    the traversal rules). Does not mutate `body`.

    A span already recognised as a surrogate this session minted on an
    earlier turn (`ResolvedSpan.is_ingress_surrogate`) is left exactly
    as-is — never re-encrypted. Every span that *is* newly substituted
    is recorded into `session`'s known-surrogate registry as part of
    this same call, so a later turn in this session can recognise it
    in turn (BUILD.md, Phase 3: "do not re-encrypt").

    `clock` is read once, at the start of this call, and that one
    `now` is used for every surrogate recorded during it — consistent
    with `SessionStore.get_or_create()`'s own "read the clock once per
    call" pattern.

    Raises:
        SurrogateDomainError: a detected span's entity type has no
            registered surrogate domain and no name-map candidate pool
            — true today for UPI and email only (Phase 4 Task 5 closed
            this gap for `PERSON`/`ORG`/`ADDRESS`) — propagates before
            any substitution is applied to the returned body, per the
            module docstring.
        FailClosedError: a Tier-2 detection failure and `fail_mode ==
            "closed"` — propagates unchanged from `cascade.detect()`.
            Under `fail_mode == "open"`, the same failure is logged and
            that region's text is sanitized with Tier-1 results only.
    """
    now = clock.now()
    substitutions: dict[FieldPath, str] = {}
    for region in walk(body):
        new_text = _sanitize_region(
            region, key_provider, session, now, correlation_id, tier2_model, fail_mode, rng
        )
        if new_text is not None:
            substitutions[region.path] = new_text

    result = rebuild(body, substitutions)
    sanitized = result.body
    assert isinstance(sanitized, dict), "rebuild() preserves a dict body's top-level type"
    return sanitized


def _sanitize_region(
    region: TextRegion,
    key_provider: KeyProvider,
    session: Session,
    now: datetime,
    correlation_id: CorrelationId,
    tier2_model: Tier2Model,
    fail_mode: FailMode,
    rng: random.Random,
) -> str | None:
    """Return `region.text` with every non-ingress span replaced by its
    surrogate, or `None` if nothing changed — so the caller can skip an
    unnecessary substitution entry for a region that is unchanged. A
    region containing only ingress-recognised spans (nothing new to
    substitute) also returns `None`, for the same reason.

    Spans are applied start-descending so each splice only ever touches
    text to the right of positions already processed. This also holds
    for same-length surrogates (guaranteed by every FF1 domain — Tier-1
    substitution is always format-preserving) without depending on
    that guarantee to be safe for out-of-order or overlapping spans,
    since `detect()` already returns a non-overlapping set. Name-map
    surrogates (Phase 4 Task 5) are *not* guaranteed same-length, but
    this remains safe regardless: descending order only requires that
    an earlier splice never shifts the offsets a later splice still
    needs to use, which holds for any-length replacement as long as
    processing goes right-to-left.
    """
    resolved_spans = detect(
        region.text, session, tier2_model, fail_mode, correlation_id=correlation_id
    )
    if not resolved_spans:
        return None

    logger = get_gateway_logger()
    new_text = region.text
    changed = False
    for resolved in sorted(resolved_spans, key=lambda r: r.span.start, reverse=True):
        if resolved.is_ingress_surrogate:
            continue
        span = resolved.span
        value = region.text[span.start : span.end]
        if span.entity_type in NAME_MAP_ENTITY_TYPES:
            # allocate_or_lookup_name() already records the resulting
            # KnownSurrogate as part of its own locked operation - no
            # separate session.record_surrogate() call here, unlike
            # the FF1 branch below.
            surrogate = session.allocate_or_lookup_name(
                value, span.entity_type, get_candidates(span.entity_type), rng, now
            )
        else:
            surrogate = engine.encrypt(span.entity_type, value, key_provider)
            session.record_surrogate(surrogate, span.entity_type, now)
        new_text = new_text[: span.start] + surrogate + new_text[span.end :]
        changed = True
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
    return new_text if changed else None
