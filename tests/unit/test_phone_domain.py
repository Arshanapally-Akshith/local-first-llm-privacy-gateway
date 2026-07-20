"""PhoneDomain: round trip across all four prefix shapes, leading-digit
preservation, format validity via the existing detector as oracle."""

import pytest

from src.core.exceptions import SurrogateDomainError
from src.detect.tier1.phone import PhoneDetector
from src.surrogate.domains.phone import PhoneDomain

_KEY = b"k" * 32


@pytest.mark.parametrize(
    "value",
    ["9876543210", "09876543210", "919876543210", "+919876543210"],
)
def test_decrypt_of_encrypt_returns_the_original_value(value: str) -> None:
    domain = PhoneDomain()

    surrogate = domain.encrypt(value, _KEY)

    assert domain.decrypt(surrogate, _KEY) == value


@pytest.mark.parametrize(
    "value",
    ["9876543210", "09876543210", "919876543210", "+919876543210"],
)
def test_leading_core_digit_is_preserved(value: str) -> None:
    domain = PhoneDomain()

    surrogate = domain.encrypt(value, _KEY)

    # The core's leading digit is always the character right before
    # the 9 permuted digits, regardless of prefix length.
    assert surrogate[-10] == value[-10]


def test_surrogate_is_still_detected_as_phone_shaped() -> None:
    domain = PhoneDomain()
    surrogate = domain.encrypt("9876543210", _KEY)

    spans = PhoneDetector().detect(surrogate)

    assert len(spans) == 1
    assert spans[0].start == 0 and spans[0].end == len(surrogate)


def test_rejects_leading_digit_outside_six_to_nine() -> None:
    domain = PhoneDomain()

    with pytest.raises(SurrogateDomainError):
        domain.encrypt("5876543210", _KEY)


def test_rejects_unrecognized_length() -> None:
    domain = PhoneDomain()

    with pytest.raises(SurrogateDomainError, match="prefix"):
        domain.encrypt("98765", _KEY)
