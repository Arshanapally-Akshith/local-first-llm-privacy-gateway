"""Application configuration.

Loads and validates all runtime settings from environment variables /
`.env` via pydantic-settings. Validation happens at `Settings()`
construction; the FastAPI entrypoint (`app/main.py`) is responsible for
constructing it at module import time, before the server binds, so a
misconfigured deployment fails at startup and never at first request
(BUILD.md Phase 0 DoD).
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated runtime configuration for the privacy gateway.

    Every field is either given an explicit, documented default or is
    required with no default. Security-relevant fields (`fail_mode`,
    `session_ttl`, `fpe_key`) are deliberately never defaulted: a silent
    default here would silently change a security property, which is the
    exact failure mode ARCHITECTURE.md's Configuration Architecture
    section forbids ("No silent security defaults").
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="forbid",
    )

    upstream_mode: Literal["mock", "live"] = "mock"
    """Which upstream the proxy forwards to. Defaults to mock: no key, no
    network, no cost — the mock upstream is the default upstream for
    every test, benchmark, and demo (ARCHITECTURE.md, Executive Summary).
    """

    upstream_base_url: str | None = None
    """Upstream endpoint. Required only when upstream_mode == "live";
    enforced by the validator below rather than given a default, since
    any default here could silently point `live` mode at nothing."""

    fpe_key: SecretStr = Field(min_length=1)
    """FF1 key (used starting Phase 2). Required, no default. Typed as
    SecretStr so it cannot appear in a repr, log line, or exception
    message by accident — see CLAUDE.md's Security Rules on the FPE key.
    """

    session_ttl: int = Field(gt=0)
    """Session map TTL, in seconds. Required, no default: TTL is a
    security control (it bounds how long PII sits in process memory), so
    its value must be a conscious operator choice, never an inherited
    one. Explicitly not defaulted per instruction."""

    fail_mode: Literal["open", "closed"]
    """Detector-failure behaviour. No default by design — see
    ARCHITECTURE.md, Error Handling: `open` silently leaks PII, `closed`
    silently causes outages, and choosing either on the operator's behalf
    would itself be the silent security default this project forbids."""

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    """Logging verbosity. Safe to default regardless of value: CLAUDE.md's
    logging rule is that no level, including DEBUG, may ever emit
    plaintext PII — the guarantee is structural, not level-gated."""

    @model_validator(mode="after")
    def _require_upstream_base_url_when_live(self) -> "Settings":
        if self.upstream_mode == "live" and not self.upstream_base_url:
            raise ValueError(
                "UPSTREAM_BASE_URL is required when UPSTREAM_MODE=live. "
                "Set it to the provider's API base URL, or switch "
                "UPSTREAM_MODE back to 'mock' to run without one."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide Settings singleton.

    Cached so configuration is validated exactly once per process and
    every caller (routes, pipeline, tests) shares one instance rather than
    re-reading the environment. Tests override this via FastAPI's
    `dependency_overrides`, never by mutating environment variables
    mid-run — see CLAUDE.md's dependency-injection rule.
    """
    return Settings()
