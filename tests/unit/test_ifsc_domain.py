"""IfscDomain: round trip, reserved literal '0' (frozen position)
preserved, format validity via the existing detector as oracle."""

import pytest

from src.core.exceptions import SurrogateDomainError
from src.detect.tier1.ifsc import IfscDetector
from src.surrogate.domains.ifsc import IfscDomain

_KEY = b"k" * 32
_VALID_IFSC = "ABCD0123456"


def test_decrypt_of_encrypt_returns_the_original_value() -> None:
    domain = IfscDomain()

    surrogate = domain.encrypt(_VALID_IFSC, _KEY)

    assert domain.decrypt(surrogate, _KEY) == _VALID_IFSC


def test_surrogate_differs_from_the_original() -> None:
    domain = IfscDomain()

    surrogate = domain.encrypt(_VALID_IFSC, _KEY)

    assert surrogate != _VALID_IFSC


def test_reserved_literal_position_is_preserved() -> None:
    domain = IfscDomain()

    surrogate = domain.encrypt(_VALID_IFSC, _KEY)

    assert surrogate[4] == "0"


def test_surrogate_is_still_detected_as_ifsc_shaped() -> None:
    domain = IfscDomain()
    surrogate = domain.encrypt(_VALID_IFSC, _KEY)

    spans = IfscDetector().detect(surrogate)

    assert len(spans) == 1
    assert spans[0].start == 0 and spans[0].end == len(surrogate)


def test_round_trips_with_digits_in_the_branch_code() -> None:
    domain = IfscDomain()
    value = "HDFC0999999"

    surrogate = domain.encrypt(value, _KEY)

    assert domain.decrypt(surrogate, _KEY) == value


def test_rejects_value_of_wrong_length() -> None:
    domain = IfscDomain()

    with pytest.raises(SurrogateDomainError, match="11-character"):
        domain.encrypt("ABCD012345", _KEY)


def test_rejects_non_zero_fifth_character() -> None:
    domain = IfscDomain()

    with pytest.raises(SurrogateDomainError):
        domain.encrypt("ABCD1123456", _KEY)
