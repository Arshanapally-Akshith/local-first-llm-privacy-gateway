"""Typed exception hierarchy for the gateway.

Callers catch categories (GatewayError subclasses), never strings.
Every message states what failed and what to do about it — never a
sensitive value (CLAUDE.md, Error Handling). Children are added only
once a phase actually raises them, not ahead of need.
"""


class GatewayError(Exception):
    """Root of the gateway's exception hierarchy. Never raised directly."""


class UpstreamError(GatewayError):
    """The configured upstream (mock or live) could not be reached, timed
    out, or returned something the proxy cannot treat as a valid
    response.

    Carries the HTTP status the proxy should return to its own caller,
    decided by whoever raises this (the upstream client). This class
    does not itself encode connection-failure-vs-timeout as separate
    subclasses — that would force every catch site to enumerate them
    instead of reading one field.
    """

    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class SurrogateDomainError(GatewayError):
    """A value cannot be represented in its entity type's FF1 domain —
    e.g. a span whose length the domain doesn't expect, or a value
    containing a character outside the domain's alphabet.

    Never caught to fall back to a pass-through: CLAUDE.md's Error
    Handling is explicit that a surrogate domain mismatch must raise,
    never silently emit the real value. The message states what
    failed and the expected shape — never the real value itself
    (CLAUDE.md: "no sensitive values in the message").
    """
