"""Basic shape tests for the exception hierarchy."""

import pytest

from src.core.exceptions import GatewayError, UpstreamError


def test_upstream_error_is_a_gateway_error() -> None:
    assert issubclass(UpstreamError, GatewayError)


def test_upstream_error_carries_status_code() -> None:
    err = UpstreamError("upstream unreachable", status_code=502)

    assert err.status_code == 502
    assert str(err) == "upstream unreachable"


def test_upstream_error_is_raiseable_and_catchable_as_gateway_error() -> None:
    with pytest.raises(GatewayError):
        raise UpstreamError("timed out", status_code=504)
