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
