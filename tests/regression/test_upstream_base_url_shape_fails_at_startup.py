"""Regression test for a Phase 7 configuration-hardening finding: a
malformed `UPSTREAM_BASE_URL` (no scheme, no host, or an unsupported
scheme) passed `Settings()` construction cleanly (it satisfied
`min_length=1`, the only constraint that existed on the field), and
`httpx.AsyncClient(base_url=...)` (`src/proxy/upstream_client.py`)
performs no shape validation of its own either — so the first sign of
trouble was a generic connection failure deep inside a real request,
never a startup failure.

Fixed by `Settings._upstream_base_url_must_be_an_absolute_http_url`
(`src/core/config.py`): a value that isn't a syntactically valid
absolute `http(s)` URL now fails `Settings()` construction itself.
"""

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from src.core.config import Settings

_MALFORMED_URL = "not a url"


def test_malformed_upstream_base_url_previously_passed_the_http_client_silently() -> None:
    # Confirms the symptom: httpx itself performs no shape validation
    # at construction, so this malformed value would previously have
    # gone undetected all the way to Settings() and beyond.
    httpx.AsyncClient(base_url=_MALFORMED_URL, timeout=30.0)


def test_malformed_upstream_base_url_fails_construction_not_first_request() -> None:
    with pytest.raises(ValidationError, match="not an absolute http"):
        Settings(
            upstream_base_url=_MALFORMED_URL,
            fpe_key=SecretStr("a-strong-operator-secret"),
            session_ttl=1800,
            fail_mode="closed",
        )
