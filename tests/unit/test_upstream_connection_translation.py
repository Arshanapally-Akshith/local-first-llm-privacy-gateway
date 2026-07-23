"""Unit tests for `_translate_upstream_connection_failure`
(`src/proxy/routes.py`) — the shared helper `_forward_non_streaming`
and `_start_streaming` both now call, replacing two byte-for-byte
identical `except httpx.TimeoutException`/`except httpx.ConnectError`
blocks (Phase 7 failure-path audit). Covers every `httpx.TransportError`
category the widened `except httpx.TransportError` clause now catches,
per the category-by-category justification in the helper's own
docstring.
"""

import httpx
import pytest

from src.core.exceptions import UpstreamError
from src.proxy.routes import _translate_upstream_connection_failure


@pytest.mark.parametrize(
    "exc",
    [
        httpx.ConnectTimeout("t"),
        httpx.ReadTimeout("t"),
        httpx.WriteTimeout("t"),
        httpx.PoolTimeout("t"),
    ],
)
def test_every_timeout_category_maps_to_504(exc: httpx.TimeoutException) -> None:
    result = _translate_upstream_connection_failure(exc)

    assert isinstance(result, UpstreamError)
    assert result.status_code == 504
    assert str(result) == "upstream request timed out"


@pytest.mark.parametrize(
    "exc",
    [
        httpx.ConnectError("t"),  # already covered before Phase 7 — unchanged behaviour
        httpx.ReadError("t"),
        httpx.WriteError("t"),
        httpx.CloseError("t"),
        httpx.LocalProtocolError("t"),
        httpx.RemoteProtocolError("t"),
        httpx.ProxyError("t"),
        httpx.UnsupportedProtocol("t"),
    ],
)
def test_every_non_timeout_transport_error_category_maps_to_502(
    exc: httpx.TransportError,
) -> None:
    result = _translate_upstream_connection_failure(exc)

    assert isinstance(result, UpstreamError)
    assert result.status_code == 502
    assert str(result) == "could not connect to upstream"


def test_translated_message_never_includes_the_raw_httpx_exception_text() -> None:
    """Regression for the Phase 7 audit's leak check: UpstreamError
    never wraps a lower layer's own exception message verbatim."""
    exc = httpx.ConnectError("connection refused to http://internal-upstream-host:9999")

    result = _translate_upstream_connection_failure(exc)

    assert "internal-upstream-host" not in str(result)
