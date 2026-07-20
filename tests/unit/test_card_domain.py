"""CardDomain: round trip, format/checksum validity via the existing
detector and checksum module as oracles, domain-mismatch handling."""

import pytest

from src.core.exceptions import SurrogateDomainError
from src.detect.tier1.card import CardDetector
from src.detect.tier1.checksum import luhn_generate_check_digit, luhn_is_valid
from src.surrogate.domains.card import CardDomain

_KEY = b"k" * 32
_PAYLOAD = "411111111111111"
_VALID_CARD = _PAYLOAD + luhn_generate_check_digit(_PAYLOAD)


def test_decrypt_of_encrypt_returns_the_original_value() -> None:
    domain = CardDomain()

    surrogate = domain.encrypt(_VALID_CARD, _KEY)

    assert domain.decrypt(surrogate, _KEY) == _VALID_CARD


def test_surrogate_is_checksum_valid() -> None:
    domain = CardDomain()

    surrogate = domain.encrypt(_VALID_CARD, _KEY)

    assert luhn_is_valid(surrogate)


def test_surrogate_is_still_detected_as_card_shaped() -> None:
    domain = CardDomain()
    surrogate = domain.encrypt(_VALID_CARD, _KEY)

    spans = CardDetector().detect(surrogate)

    assert len(spans) == 1
    assert spans[0].start == 0 and spans[0].end == len(surrogate)


def test_round_trips_at_the_shortest_supported_length() -> None:
    domain = CardDomain()
    payload = "41111111111"  # 11 digits -> 12-digit card
    value = payload + luhn_generate_check_digit(payload)

    surrogate = domain.encrypt(value, _KEY)

    assert domain.decrypt(surrogate, _KEY) == value


def test_rejects_value_shorter_than_minimum() -> None:
    domain = CardDomain()

    with pytest.raises(SurrogateDomainError, match="12-19"):
        domain.encrypt("1234567890", _KEY)


def test_rejects_non_digit_value() -> None:
    domain = CardDomain()

    with pytest.raises(SurrogateDomainError):
        domain.encrypt("411111111111111A", _KEY)
