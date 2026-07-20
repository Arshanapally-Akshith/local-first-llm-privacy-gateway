"""AadhaarDomain: round trip, format/checksum validity (via the
existing detector and checksum module as oracles — no second
"is this Aadhaar-shaped" implementation), and domain-mismatch
handling.

Reserved-range compliance is explicitly NOT tested here — not a
missing test, but an untestable, permanently retired requirement.
See docs/DECISIONS.md, 2026-07-20, "Aadhaar reserved-range
requirement retired as mathematically unsatisfiable."
"""

import pytest

from src.core.exceptions import SurrogateDomainError
from src.detect.tier1.aadhaar import AadhaarDetector
from src.detect.tier1.checksum import verhoeff_generate_check_digit, verhoeff_is_valid
from src.surrogate.domains.aadhaar import AadhaarDomain

_KEY = b"k" * 32
_PAYLOAD = "23456789012"
_VALID_AADHAAR = _PAYLOAD + verhoeff_generate_check_digit(_PAYLOAD)


def test_decrypt_of_encrypt_returns_the_original_value() -> None:
    domain = AadhaarDomain()

    surrogate = domain.encrypt(_VALID_AADHAAR, _KEY)

    assert domain.decrypt(surrogate, _KEY) == _VALID_AADHAAR


def test_surrogate_differs_from_the_original() -> None:
    domain = AadhaarDomain()

    surrogate = domain.encrypt(_VALID_AADHAAR, _KEY)

    assert surrogate != _VALID_AADHAAR


def test_surrogate_is_checksum_valid() -> None:
    domain = AadhaarDomain()

    surrogate = domain.encrypt(_VALID_AADHAAR, _KEY)

    assert verhoeff_is_valid(surrogate)


def test_surrogate_is_still_detected_as_aadhaar_shaped() -> None:
    # Reuses the already-tested detector as the format-validity oracle
    # instead of re-implementing "is this Aadhaar-shaped" here.
    domain = AadhaarDomain()
    surrogate = domain.encrypt(_VALID_AADHAAR, _KEY)

    spans = AadhaarDetector().detect(surrogate)

    assert len(spans) == 1
    assert spans[0].start == 0 and spans[0].end == len(surrogate)


def test_different_keys_produce_different_surrogates() -> None:
    domain = AadhaarDomain()

    a = domain.encrypt(_VALID_AADHAAR, _KEY)
    b = domain.encrypt(_VALID_AADHAAR, b"j" * 32)

    assert a != b


def test_rejects_value_of_wrong_length() -> None:
    domain = AadhaarDomain()

    with pytest.raises(SurrogateDomainError, match="12-digit"):
        domain.encrypt("123456789", _KEY)


def test_rejects_non_digit_value() -> None:
    domain = AadhaarDomain()

    with pytest.raises(SurrogateDomainError):
        domain.encrypt("2345678901AB", _KEY)
