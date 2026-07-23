"""Unit tests for `app.main`'s GatewayError exception-handler dispatch
layer, called directly as plain coroutines (every handler ignores its
`Request` argument, so a minimal bare-scope `Request` stands in for a
real one) — this exercises the handlers as units, distinct from
`tests/integration/test_chat_completions_route.py`, which proves what
actually reaches them through the real request pipeline.
"""

import json

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse

from app.main import (
    _handle_fail_closed_error,
    _handle_gateway_error,
    _handle_surrogate_domain_error,
    _handle_upstream_error,
)
from src.core.exceptions import (
    DetectionError,
    GatewayError,
    NameListExhaustedError,
    RehydrationError,
    SurrogateDomainError,
    UpstreamError,
)
from src.core.fail_mode import FailClosedError

_REQUEST = Request(scope={"type": "http"})


def _body(response: JSONResponse) -> object:
    return json.loads(bytes(response.body))


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_upstream_error_handler_uses_the_exceptions_own_status_code() -> None:
    exc = UpstreamError("could not connect to upstream", status_code=502)

    response = await _handle_upstream_error(_REQUEST, exc)

    assert response.status_code == 502
    assert _body(response) == {"error": "could not connect to upstream"}


@pytest.mark.anyio
async def test_upstream_error_handler_reflects_a_different_status_code_too() -> None:
    """Proves the handler reads `exc.status_code` rather than a
    hardcoded value — 504 is a different code than the test above."""
    exc = UpstreamError("upstream request timed out", status_code=504)

    response = await _handle_upstream_error(_REQUEST, exc)

    assert response.status_code == 504


@pytest.mark.anyio
async def test_surrogate_domain_error_handler_returns_500() -> None:
    exc = SurrogateDomainError("no surrogate domain registered for entity_type=UPI")

    response = await _handle_surrogate_domain_error(_REQUEST, exc)

    assert response.status_code == 500
    assert _body(response) == {"error": "no surrogate domain registered for entity_type=UPI"}


@pytest.mark.anyio
async def test_fail_closed_error_handler_returns_503() -> None:
    exc = FailClosedError("detection.tier2_failed failed under FAIL_MODE=closed: RuntimeError")

    response = await _handle_fail_closed_error(_REQUEST, exc)

    assert response.status_code == 503
    assert _body(response) == {
        "error": "detection.tier2_failed failed under FAIL_MODE=closed: RuntimeError"
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    "exc",
    [
        DetectionError(
            "Tier2Detector(entity_type=PERSON) received an out-of-bounds match "
            "(start=0, end=99) for a text region of length 10"
        ),
        RehydrationError(
            "known-surrogate registry has entity_type=PERSON (a name-map type) "
            "for a surrogate with no matching entry in this session's reverse name map"
        ),
        NameListExhaustedError("session has assigned all 3 candidates and needs one more"),
    ],
)
async def test_gateway_error_catch_all_returns_500_for_types_with_no_specific_handler(
    exc: GatewayError,
) -> None:
    """Regression for the Phase 7 audit finding: DetectionError,
    RehydrationError, and NameListExhaustedError previously had no
    registered handler at all and fell through to Starlette's bare,
    unstructured default 500."""
    response = await _handle_gateway_error(_REQUEST, exc)

    assert response.status_code == 500
    assert _body(response) == {"error": str(exc)}
