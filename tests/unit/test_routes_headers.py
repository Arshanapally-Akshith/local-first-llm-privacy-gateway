"""Unit tests for the hop-by-hop header stripping helper."""

import httpx

from src.proxy.routes import _forwardable_headers


def test_hop_by_hop_headers_are_stripped() -> None:
    headers = httpx.Headers(
        {
            "content-type": "application/json",
            "connection": "keep-alive",
            "transfer-encoding": "chunked",
            "x-custom-provider-header": "value",
        }
    )

    result = _forwardable_headers(headers)

    assert result == {
        "content-type": "application/json",
        "x-custom-provider-header": "value",
    }


def test_stripping_is_case_insensitive() -> None:
    headers = httpx.Headers({"Connection": "close", "Content-Type": "text/event-stream"})

    result = _forwardable_headers(headers)

    assert "connection" not in result
    assert result["content-type"] == "text/event-stream"


def test_no_hop_by_hop_headers_present_returns_everything() -> None:
    headers = httpx.Headers({"content-type": "application/json"})

    assert _forwardable_headers(headers) == {"content-type": "application/json"}
