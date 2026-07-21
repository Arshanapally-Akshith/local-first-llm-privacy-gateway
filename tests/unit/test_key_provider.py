"""SettingsKeyProvider: deterministic, 32-byte, derived from
Settings.fpe_key — never the raw secret itself."""

from pydantic import SecretStr

from src.core.config import Settings
from src.surrogate.key_provider import SettingsKeyProvider, get_key_provider


def _settings(fpe_key: str) -> Settings:
    return Settings(
        upstream_base_url="http://127.0.0.1:8081",
        fpe_key=SecretStr(fpe_key),
        session_ttl=1800,
        fail_mode="closed",
    )


def test_get_key_returns_32_bytes() -> None:
    provider = SettingsKeyProvider(_settings("some-operator-secret"))

    assert len(provider.get_key()) == 32


def test_get_key_is_deterministic_for_the_same_secret() -> None:
    provider_a = SettingsKeyProvider(_settings("same-secret"))
    provider_b = SettingsKeyProvider(_settings("same-secret"))

    assert provider_a.get_key() == provider_b.get_key()


def test_get_key_differs_for_different_secrets() -> None:
    provider_a = SettingsKeyProvider(_settings("secret-one"))
    provider_b = SettingsKeyProvider(_settings("secret-two"))

    assert provider_a.get_key() != provider_b.get_key()


def test_get_key_never_returns_the_raw_secret_bytes() -> None:
    raw = "some-operator-secret"
    provider = SettingsKeyProvider(_settings(raw))

    assert raw.encode("utf-8") != provider.get_key()


def test_get_key_provider_returns_the_same_instance_across_calls() -> None:
    """`@lru_cache`, mirroring `upstream_client.get_upstream_client()` —
    one KeyProvider per process, not one per request."""
    assert get_key_provider() is get_key_provider()
