"""engine.encrypt/decrypt: registry lookup + KeyProvider orchestration,
against a fake KeyProvider (no real Settings needed here)."""

import pytest

from src.core.exceptions import SurrogateDomainError
from src.detect.tier1.checksum import verhoeff_generate_check_digit
from src.surrogate import engine


class _FakeKeyProvider:
    def __init__(self, key: bytes) -> None:
        self._key = key

    def get_key(self) -> bytes:
        return self._key


_KEY_PROVIDER = _FakeKeyProvider(b"k" * 32)
_PAYLOAD = "23456789012"
_VALID_AADHAAR = _PAYLOAD + verhoeff_generate_check_digit(_PAYLOAD)


def test_encrypt_then_decrypt_round_trips() -> None:
    surrogate = engine.encrypt("AADHAAR", _VALID_AADHAAR, _KEY_PROVIDER)

    assert engine.decrypt("AADHAAR", surrogate, _KEY_PROVIDER) == _VALID_AADHAAR


def test_encrypt_produces_a_different_value() -> None:
    surrogate = engine.encrypt("AADHAAR", _VALID_AADHAAR, _KEY_PROVIDER)

    assert surrogate != _VALID_AADHAAR


def test_raises_for_a_type_with_no_registered_domain() -> None:
    with pytest.raises(SurrogateDomainError):
        engine.encrypt("UPI", "someone@fakebank", _KEY_PROVIDER)


def test_uses_the_key_from_the_provided_key_provider() -> None:
    other_provider = _FakeKeyProvider(b"j" * 32)

    a = engine.encrypt("AADHAAR", _VALID_AADHAAR, _KEY_PROVIDER)
    b = engine.encrypt("AADHAAR", _VALID_AADHAAR, other_provider)

    assert a != b
