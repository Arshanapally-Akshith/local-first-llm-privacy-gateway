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

from pydantic import Field, SecretStr
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

    upstream_base_url: str = Field(min_length=1)
    """Upstream endpoint. Required in both mock and live modes, with no
    code-level default — mock and live upstreams are interchangeable
    purely by which URL is configured (ARCHITECTURE.md), so inventing a
    default for the mock case would be exactly the kind of hidden
    runtime default this project's configuration rules forbid. The
    value to use for mock mode is documented, explicitly, in
    .env.example."""

    upstream_timeout: float = Field(gt=0, default=30.0)
    """Upstream request timeout, in seconds. Defaulted (unlike
    fail_mode/session_ttl/fpe_key): a missing timeout would still need
    *some* value for the HTTP client to function at all, and getting it
    wrong is a reliability question, not a security one — no default
    here silently changes what the gateway does or doesn't sanitise.
    30.0 is a guess, not a measurement; revisit once Phase 7's latency
    harness has real numbers."""

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

    ner_model: str = Field(min_length=1, default="urchade/gliner_multi_pii-v1")
    """Tier-2 model identifier (Phase 4). Defaulted, unlike
    fail_mode/session_ttl/fpe_key: choosing a model is not itself a
    security-relevant trade-off the way FAIL_MODE is, so a sensible
    default (unlike those three) doesn't hide a silent security choice —
    it just saves an operator a step, the same reasoning `upstream_timeout`
    already uses. This specific default was chosen by measurement, not
    guessed: see `docs/DECISIONS.md`, Phase 4 Task 2, for the evaluation
    against `gliner_small-v2.1` and other GLiNER-class checkpoints that
    picked it (concentrated ADDRESS-recall and false-positive-rate
    improvements on a synthetic corpus, weighed against its larger RAM
    footprint)."""

    ner_warmup: bool = Field(default=True)
    """Whether to load and run one warm-up inference through the Tier-2
    model at startup, before the server binds. Defaulted `True`: the
    failure mode of warming by default is a slightly slower startup;
    the failure mode of *not* warming by default is BUILD.md's own
    named danger — "cold start hides inside p50" — silently, on every
    deployment that didn't think to flip a flag. Unlike FAIL_MODE, only
    one side of this default is actually safe, so (per the same
    reasoning `src/session/store.py`'s `DEFAULT_MAX_SESSIONS` already
    documents) a defaulted, overridable flag is appropriate here, not a
    forced explicit choice."""


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
