"""Phase 4 closeout: the literal BUILD.md Phase 4 gate, proven against
the real GLiNER model (`urchade/gliner_multi_pii-v1`) through the real
HTTP route — not a fake, and not just at the `cascade.detect()`/
`sanitize()` unit level (`tests/unit/test_cascade.py`,
`tests/integration/test_tier2_real_model.py` already prove the
mechanics; this proves BUILD.md's own gate sentence, verbatim):

"Hinglish sentence with a name, an org, an address, and a PAN ->
correct spans, correct tier attribution, surrogates consistent across
turns."

The sentence below is not invented blind — it was run directly against
`get_tier2_model()` before this test was written (see
`docs/DECISIONS.md`, Phase 4 closeout) to confirm the real model
actually resolves all three Tier-2 types in it, so this test's
assertions are grounded in observed behaviour, matching this project's
own "measure, don't assume" standard for GLiNER's Hinglish/code-switched
capability rather than a hopeful guess.

Marked `real_model` (loads real weights) — excluded from the default
run, same as `test_tier2_real_model.py`.
"""

import json
import logging
from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from src.core.logging import PiiSafeFormatter
from src.detect.tier2.gliner_model import get_tier2_model
from src.mock_upstream.main import app as mock_app
from src.proxy.upstream_client import get_upstream_client

pytestmark = pytest.mark.real_model

_VALID_PAN = "AAAPL1234C"
_REAL_NAME = "Ramesh Kumar"
_REAL_ORG = "Bharat Textiles"
_REAL_ADDRESS = "14 MG Road, Bengaluru"
_CONTENT = (
    f"Mera naam {_REAL_NAME} hai aur main {_REAL_ORG} mein kaam karta hoon, "
    f"humara office {_REAL_ADDRESS} mein hai, PAN {_VALID_PAN} hai"
)


class _CapturingTransport(httpx.AsyncBaseTransport):
    """Same technique as `test_phase_3_gate.py`/`test_sanitize_integration.py`
    — records every request body that actually crossed to "upstream"."""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        self._inner = inner
        self.captured_bodies: list[bytes] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.captured_bodies.append(request.content)
        return await self._inner.handle_async_request(request)


def _override_with_capturing_mock_upstream() -> _CapturingTransport:
    capturing = _CapturingTransport(httpx.ASGITransport(app=mock_app))

    def _get_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=capturing, base_url="http://mock-upstream")

    app.dependency_overrides[get_upstream_client] = _get_client
    return capturing


@pytest.fixture(autouse=True)
def _clear_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.pop(get_upstream_client, None)
    app.dependency_overrides.pop(get_tier2_model, None)


def test_phase_4_gate_hinglish_name_org_address_and_pan(
    captured_records: list[logging.LogRecord],
) -> None:
    # tests/conftest.py's autouse fixture overrides get_tier2_model with
    # a zero-cost fake for every test by default (see that fixture's own
    # docstring) - this gate is the one deliberate exception: it needs
    # the *real* model, since the whole point is proving real GLiNER
    # behaviour, not a fake's.
    app.dependency_overrides.pop(get_tier2_model, None)
    capturing = _override_with_capturing_mock_upstream()
    client = TestClient(app, headers={"X-Session-Id": "phase-4-gate"})

    def _send() -> httpx.Response:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4",
                "messages": [{"role": "user", "content": _CONTENT}],
                "stream": False,
            },
        )
        assert response.status_code == 200
        return response

    # Turn 1.
    response_1 = _send()
    assert response_1.json()["choices"][0]["message"]["content"] == _CONTENT

    # Turn 2 - an independent request on the same session, same real
    # values. "Surrogates consistent across turns" (BUILD.md) means:
    # the exact same sanitized body crosses to upstream both times -
    # FF1 statelessness for the PAN, session-map idempotency for
    # PERSON/ORG/ADDRESS, together, in one assertion.
    response_2 = _send()
    assert response_2.json()["choices"][0]["message"]["content"] == _CONTENT

    assert len(capturing.captured_bodies) == 2
    upstream_saw_1 = json.loads(capturing.captured_bodies[0])
    upstream_saw_2 = json.loads(capturing.captured_bodies[1])
    sanitized_content_1 = upstream_saw_1["messages"][0]["content"]
    sanitized_content_2 = upstream_saw_2["messages"][0]["content"]

    # Correct spans: every real value is gone from what upstream saw,
    # both turns.
    for real_value in (_REAL_NAME, _REAL_ORG, _REAL_ADDRESS, _VALID_PAN):
        assert real_value not in sanitized_content_1
        assert real_value not in sanitized_content_2

    # Consistent across turns: byte-identical sanitized bodies for
    # byte-identical real input, both entity mechanisms at once.
    assert sanitized_content_1 == sanitized_content_2

    # Correct tier attribution: the PAN resolved via Tier 1 (checksum,
    # deterministic); PERSON/ORG/ADDRESS resolved via Tier 2 (the real
    # model) - both observed directly in the structured log output, not
    # inferred.
    formatter = PiiSafeFormatter()
    span_events = [
        json.loads(formatter.format(r))
        for r in captured_records
        if getattr(r, "event", None) == "pipeline.span_sanitized"
    ]
    tiers_by_entity_type = {e["entity_type"]: e["tier"] for e in span_events}
    assert tiers_by_entity_type["PAN"] == 1
    assert tiers_by_entity_type["PERSON"] == 2
    assert tiers_by_entity_type["ORG"] == 2
    assert tiers_by_entity_type["ADDRESS"] == 2
