"""Regression test for the defect documented in `docs/LIMITATIONS.md`
("Tier-2 can misclassify a message's literal `role` field as
`PERSON`") and `docs/DECISIONS.md` (2026-07-22): Tier-2 misclassifying
a message's literal `role` value corrupted the OpenAI role enum on an
otherwise ordinary, non-adversarial request, because `sanitize()` had
no notion of which text-bearing fields were wire-protocol metadata
rather than natural-language content.

Symptom: `sanitize()` could forward `{"role": "Krishna Chowdhury", ...}`
to the upstream provider in place of `{"role": "user", ...}`.

Fixed in Phase 7 by `src/pipeline/protocol_fields.py`, wired into
`src/pipeline/sanitize.py::sanitize()`. This test reproduces the exact
scenario end-to-end — through the real ASGI app, the real `sanitize()`
pipeline, and a mock upstream behind a `CapturingTransport` — with a
stub `Tier2Model` that deterministically reproduces the real GLiNER
misfire, so the regression does not depend on loading real model
weights.
"""

import json
from collections.abc import Iterator, Sequence

import pytest
from fastapi.testclient import TestClient

from adversarial.runner.gateway_client import CapturingTransport, override_with_capturing_mock_upstream
from app.main import app
from src.core.types import Offset
from src.detect.tier1.checksum import verhoeff_generate_check_digit
from src.detect.tier2.gliner_model import get_tier2_model
from src.detect.tier2.model import ModelEntityMatch
from src.mock_upstream.main import app as mock_app
from src.proxy.upstream_client import get_upstream_client

_PAYLOAD = "23456789012"
_VALID_AADHAAR = _PAYLOAD + verhoeff_generate_check_digit(_PAYLOAD)


class _RoleMisfiringTier2Model:
    """Reproduces the exact defect this test guards against:
    `find_entities("user")` returns a `PERSON` match spanning the
    entire string — the same failure mode real GLiNER was observed to
    produce during Phase 6 (`docs/DECISIONS.md`, 2026-07-22)."""

    def find_entities(self, text: str) -> Sequence[ModelEntityMatch]:
        if text == "user":
            return [ModelEntityMatch(start=Offset(0), end=Offset(len(text)), entity_type="PERSON")]
        return []


@pytest.fixture(autouse=True)
def _clear_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.pop(get_upstream_client, None)
    app.dependency_overrides.pop(get_tier2_model, None)


def test_role_field_reaches_upstream_unmodified_despite_a_tier2_misfire_on_it() -> None:
    app.dependency_overrides[get_tier2_model] = _RoleMisfiringTier2Model
    capturing: CapturingTransport = override_with_capturing_mock_upstream(app, mock_app)
    client = TestClient(app, headers={"X-Session-Id": "role-regression-session"})

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "hello there"}],
            "stream": False,
        },
    )

    assert response.status_code == 200
    upstream_saw = json.loads(capturing.captured_bodies[0])
    assert upstream_saw["messages"][0]["role"] == "user"


def test_content_in_the_same_message_is_still_sanitized_despite_the_role_exemption() -> None:
    """The exemption that fixes the symptom above must not become a
    blanket "skip detection on this message" -- real PII in `content`
    alongside the misfiring role must still be caught."""
    app.dependency_overrides[get_tier2_model] = _RoleMisfiringTier2Model
    capturing: CapturingTransport = override_with_capturing_mock_upstream(app, mock_app)
    client = TestClient(app, headers={"X-Session-Id": "role-regression-session-2"})

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4",
            "messages": [{"role": "user", "content": f"Aadhaar {_VALID_AADHAAR}"}],
            "stream": False,
        },
    )

    assert response.status_code == 200
    upstream_saw = json.loads(capturing.captured_bodies[0])
    assert upstream_saw["messages"][0]["role"] == "user"
    assert _VALID_AADHAAR not in upstream_saw["messages"][0]["content"]
