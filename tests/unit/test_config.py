"""core.config.Settings: validated at construction — every required
field, every documented default, every constraint (`gt=0`, `min_length`,
`Literal` membership, `extra="forbid"`), and the two Phase 7 hardening
validators (`session_ttl` must fit a `timedelta`, `upstream_base_url`
must be a shape-valid absolute http(s) URL). `Settings()` is constructed
directly with kwargs throughout, exactly like `test_key_provider.py`'s
own `_settings()` helper — this still runs every `@field_validator`,
since pydantic validates on construction regardless of how field values
arrive.

`_env_file=None` is passed on every construction in this file
(pydantic-settings' own per-instance override) so these tests exercise
only the kwargs given plus `Settings`'s own coded defaults — never a
developer's local, untracked `.env` file, whose contents (if any) must
not be able to change whether this suite passes.
"""

from datetime import timedelta

import pytest
from pydantic import SecretStr, ValidationError

from src.core.config import Settings, get_settings

_REQUIRED_KWARGS: dict[str, object] = {
    "upstream_base_url": "http://127.0.0.1:8081",
    "fpe_key": SecretStr("a-strong-operator-secret"),
    "session_ttl": 1800,
    "fail_mode": "closed",
}


def _settings(**overrides: object) -> Settings:
    return Settings(**{**_REQUIRED_KWARGS, **overrides, "_env_file": None})  # type: ignore[arg-type]


# --- Valid configuration -----------------------------------------------


def test_constructs_with_only_required_fields_and_documented_defaults() -> None:
    settings = _settings()

    assert settings.upstream_mode == "mock"
    assert settings.upstream_timeout == 30.0
    assert settings.log_level == "INFO"
    assert settings.ner_model == "urchade/gliner_multi_pii-v1"
    assert settings.ner_warmup is True


def test_accepts_explicit_override_of_every_defaulted_field() -> None:
    settings = _settings(
        upstream_mode="live",
        upstream_timeout=5.0,
        log_level="DEBUG",
        ner_model="some/other-model",
        ner_warmup=False,
    )

    assert settings.upstream_mode == "live"
    assert settings.upstream_timeout == 5.0
    assert settings.log_level == "DEBUG"
    assert settings.ner_model == "some/other-model"
    assert settings.ner_warmup is False


def test_get_settings_returns_the_same_cached_instance_across_calls() -> None:
    """`@lru_cache`, mirroring `get_key_provider()`/`get_upstream_client()`'s
    own singleton pattern — one Settings per process."""
    assert get_settings() is get_settings()


def test_fpe_key_never_appears_in_settings_repr_or_str() -> None:
    """Regression for the explicit claim in `Settings.fpe_key`'s own
    docstring: "Typed as SecretStr so it cannot appear in a repr, log
    line, or exception message by accident." """
    raw = "do-not-leak-this-value"
    settings = _settings(fpe_key=SecretStr(raw))

    assert raw not in repr(settings)
    assert raw not in str(settings)


# --- Invalid: missing required fields -----------------------------------


@pytest.mark.parametrize(
    ("missing", "env_var"),
    [
        ("upstream_base_url", "UPSTREAM_BASE_URL"),
        ("fpe_key", "FPE_KEY"),
        ("session_ttl", "SESSION_TTL"),
        ("fail_mode", "FAIL_MODE"),
    ],
)
def test_missing_required_field_fails_construction(
    missing: str, env_var: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`tests/conftest.py` sets a process-wide placeholder for each of
    these four env vars, and this developer's own local `.env` sets
    them too, so omitting a kwarg alone isn't "missing" while either
    fallback is live (`BaseSettings` checks the environment, then
    `.env`, before a field counts as absent). Both are neutralized for
    the duration of this test: the env var is deleted, and `_env_file`
    is overridden to `None` so `.env` itself is never consulted."""
    monkeypatch.delenv(env_var, raising=False)
    kwargs: dict[str, object] = {k: v for k, v in _REQUIRED_KWARGS.items() if k != missing}
    kwargs["_env_file"] = None

    with pytest.raises(ValidationError):
        Settings(**kwargs)  # type: ignore[arg-type]


# --- Invalid: constraint violations on existing fields -------------------


@pytest.mark.parametrize("value", [0, -1, -1800])
def test_session_ttl_non_positive_fails_construction(value: int) -> None:
    with pytest.raises(ValidationError):
        _settings(session_ttl=value)


@pytest.mark.parametrize("value", ["OPEN", "Open", "maybe", ""])
def test_fail_mode_rejects_anything_but_the_two_exact_literals(value: str) -> None:
    with pytest.raises(ValidationError):
        _settings(fail_mode=value)


def test_upstream_mode_rejects_a_value_outside_mock_or_live() -> None:
    with pytest.raises(ValidationError):
        _settings(upstream_mode="production")


def test_unknown_env_field_fails_construction() -> None:
    """`extra="forbid"` regression: a typo'd/unrecognized field must not
    be silently ignored."""
    with pytest.raises(ValidationError):
        _settings(this_field_does_not_exist="x")


def test_fpe_key_empty_string_fails_construction() -> None:
    with pytest.raises(ValidationError):
        _settings(fpe_key=SecretStr(""))


@pytest.mark.parametrize("value", [0.0, -1.0])
def test_upstream_timeout_non_positive_fails_construction(value: float) -> None:
    with pytest.raises(ValidationError):
        _settings(upstream_timeout=value)


def test_ner_model_empty_string_fails_construction() -> None:
    with pytest.raises(ValidationError):
        _settings(ner_model="")


# --- Invalid: Phase 7 hardening — session_ttl must fit a timedelta -------


def test_session_ttl_too_large_to_fit_a_timedelta_fails_construction() -> None:
    """Regression: this previously passed `Settings()` (satisfies
    `gt=0`) and only raised a bare `OverflowError` inside
    `get_session_store()` on the first request."""
    too_large = 86_400 * 1_000_000_000  # one day past timedelta's max of 999,999,999 days

    with pytest.raises(ValidationError, match="does not fit in a timedelta"):
        _settings(session_ttl=too_large)


def test_session_ttl_just_under_the_timedelta_boundary_succeeds() -> None:
    """Proves the validator isn't overly conservative: a large-but-valid
    TTL (comfortably within `timedelta`'s own max of 999,999,999 days)
    is accepted."""
    large_but_valid = 86_400 * 999_999_999

    settings = _settings(session_ttl=large_but_valid)

    assert settings.session_ttl == large_but_valid
    timedelta(seconds=settings.session_ttl)  # does not raise


def test_session_ttl_minimum_valid_value_succeeds() -> None:
    settings = _settings(session_ttl=1)

    assert settings.session_ttl == 1


# --- Invalid: Phase 7 hardening — upstream_base_url must be shape-valid --


@pytest.mark.parametrize(
    "value",
    [
        "not a url",
        "127.0.0.1:8081",  # no scheme
        "http://",  # scheme but no host
        "ftp://example.com",  # unsupported scheme
        "://missing-scheme",
    ],
)
def test_upstream_base_url_shape_violations_fail_construction(value: str) -> None:
    """Regression: these previously passed both `Settings()` (satisfies
    `min_length=1`) and `httpx.AsyncClient()` construction silently,
    surfacing only as a connection failure deep inside a real request."""
    with pytest.raises(ValidationError, match="not an absolute http"):
        _settings(upstream_base_url=value)


@pytest.mark.parametrize(
    "value",
    ["http://127.0.0.1:8081", "https://api.example.com", "http://localhost:8080/v1"],
)
def test_upstream_base_url_valid_http_and_https_succeed(value: str) -> None:
    settings = _settings(upstream_base_url=value)

    assert settings.upstream_base_url == value


# --- Edge cases -----------------------------------------------------------


@pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
def test_log_level_accepts_every_documented_level(level: str) -> None:
    settings = _settings(log_level=level)

    assert settings.log_level == level
