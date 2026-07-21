"""The Tier-2 startup-warmup lifespan hook's own conditional logic
(Phase 4 Task 2) - `_warm_tier2_model` itself is mocked out here, so
this file needs no real model and stays in the default, fast test
suite. `tests/integration/test_tier2_real_model.py` (marked
`real_model`, excluded by default - see `pytest.ini`) proves what
`_warm_tier2_model` actually does against the real model.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app


@pytest.fixture()
def mock_warm(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock()
    monkeypatch.setattr(main_module, "_warm_tier2_model", mock)
    return mock


def test_lifespan_warms_the_model_when_ner_warmup_is_enabled(
    monkeypatch: pytest.MonkeyPatch, mock_warm: MagicMock
) -> None:
    monkeypatch.setattr(main_module.settings, "ner_warmup", True)

    with TestClient(app):
        pass

    mock_warm.assert_called_once()


def test_lifespan_skips_warmup_when_ner_warmup_is_disabled(
    monkeypatch: pytest.MonkeyPatch, mock_warm: MagicMock
) -> None:
    monkeypatch.setattr(main_module.settings, "ner_warmup", False)

    with TestClient(app):
        pass

    mock_warm.assert_not_called()
