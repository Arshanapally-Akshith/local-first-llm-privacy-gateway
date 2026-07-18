"""Validates the mock's SSE chunk shape against a hand-built, publicly
documented reference — see tests/fixtures/openai_stream_capture.md for
provenance: not a live capture, no paid key used anywhere.

Compares key structure only (`set(dict.keys())`), never exact IDs,
timestamps, or content — those are legitimately different between the
fixture and the mock's own output.
"""

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from src.mock_upstream.main import app

client = TestClient(app)
_FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "openai_stream_capture.jsonl"


def _fixture_chunks() -> list[dict[str, Any]]:
    with _FIXTURE_PATH.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _mock_chunks() -> list[dict[str, Any]]:
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "Hello!"}],
            "stream": True,
        },
    )
    chunks = []
    for line in response.text.splitlines():
        if line.startswith("data: ") and line != "data: [DONE]":
            chunks.append(json.loads(line[len("data: ") :]))
    return chunks


def test_mock_top_level_keys_match_fixture() -> None:
    fixture_keys = set(_fixture_chunks()[0].keys())
    mock_keys = set(_mock_chunks()[0].keys())

    assert mock_keys == fixture_keys


def test_mock_choices_entry_keys_match_fixture() -> None:
    fixture_choice_keys = set(_fixture_chunks()[0]["choices"][0].keys())
    mock_choice_keys = set(_mock_chunks()[0]["choices"][0].keys())

    assert mock_choice_keys == fixture_choice_keys


def test_mock_role_establishing_delta_keys_match_fixture() -> None:
    fixture_first_delta_keys = set(_fixture_chunks()[0]["choices"][0]["delta"].keys())
    mock_first_delta_keys = set(_mock_chunks()[0]["choices"][0]["delta"].keys())

    assert mock_first_delta_keys == fixture_first_delta_keys


def test_mock_final_chunk_finish_reason_matches_fixture_shape() -> None:
    fixture_final = _fixture_chunks()[-1]
    mock_final = _mock_chunks()[-1]

    assert fixture_final["choices"][0]["finish_reason"] == "stop"
    assert mock_final["choices"][0]["finish_reason"] == "stop"
