"""PanDomain: round trip, category-letter (frozen position) preserved,
format validity via the existing detector as oracle."""

import pytest

from src.core.exceptions import SurrogateDomainError
from src.detect.tier1.pan import PanDetector
from src.surrogate.domains.pan import PanDomain

_KEY = b"k" * 32
_VALID_PAN = "ABCPE1234F"


def test_decrypt_of_encrypt_returns_the_original_value() -> None:
    domain = PanDomain()

    surrogate = domain.encrypt(_VALID_PAN, _KEY)

    assert domain.decrypt(surrogate, _KEY) == _VALID_PAN


def test_surrogate_differs_from_the_original() -> None:
    domain = PanDomain()

    surrogate = domain.encrypt(_VALID_PAN, _KEY)

    assert surrogate != _VALID_PAN


def test_category_letter_position_is_preserved() -> None:
    domain = PanDomain()

    surrogate = domain.encrypt(_VALID_PAN, _KEY)

    assert surrogate[3] == _VALID_PAN[3]


def test_surrogate_is_still_detected_as_pan_shaped() -> None:
    domain = PanDomain()
    surrogate = domain.encrypt(_VALID_PAN, _KEY)

    spans = PanDetector().detect(surrogate)

    assert len(spans) == 1
    assert spans[0].start == 0 and spans[0].end == len(surrogate)


def test_round_trips_for_every_documented_category_letter() -> None:
    domain = PanDomain()
    for category in "PCHABGJLFT":
        value = f"ABC{category}E1234F"

        surrogate = domain.encrypt(value, _KEY)

        assert domain.decrypt(surrogate, _KEY) == value
        assert surrogate[3] == category


def test_rejects_value_of_wrong_length() -> None:
    domain = PanDomain()

    with pytest.raises(SurrogateDomainError, match="10-character"):
        domain.encrypt("ABCPE123F", _KEY)


def test_rejects_lowercase_value() -> None:
    domain = PanDomain()

    with pytest.raises(SurrogateDomainError):
        domain.encrypt("abcpe1234f", _KEY)
