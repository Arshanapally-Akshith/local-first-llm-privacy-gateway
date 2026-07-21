"""Injected access to the FF1 key — never read `Settings.fpe_key`
directly from domain or engine code (CLAUDE.md: "Anything with a
clock, a key, a model, a network call, or randomness is injected,
never reached for globally").
"""

import hashlib
from functools import lru_cache
from typing import Protocol

from src.core.config import Settings, get_settings


class KeyProvider(Protocol):
    def get_key(self) -> bytes:
        """Return a 32-byte AES-256 key for FF1's underlying block
        cipher. Must be pure and side-effect-free: same provider,
        same key, every call."""
        ...


class SettingsKeyProvider:
    """`KeyProvider` backed by `Settings.fpe_key`.

    `fpe_key` is an operator-supplied secret of arbitrary length
    (`SecretStr`, `min_length=1`), not necessarily 16/24/32 bytes —
    the lengths AES actually accepts. SHA-256 derives a fixed 32-byte
    AES-256 key from it deterministically. This is a plain digest, not
    a password-hardened KDF (PBKDF2/scrypt/Argon2): `FPE_KEY` is meant
    to be an operator-chosen strong secret rather than a
    human-memorable password needing brute-force resistance, so the
    extra iteration cost of a hardening KDF buys nothing here.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def get_key(self) -> bytes:
        raw = self._settings.fpe_key.get_secret_value().encode("utf-8")
        return hashlib.sha256(raw).digest()


@lru_cache
def get_key_provider() -> KeyProvider:
    """FastAPI dependency: one `KeyProvider` per process, mirroring
    `upstream_client.get_upstream_client()`'s exact shape. Tests
    override this via FastAPI's `dependency_overrides`, never by
    patching this function's internals (CLAUDE.md's dependency-
    injection rule)."""
    return SettingsKeyProvider(get_settings())
