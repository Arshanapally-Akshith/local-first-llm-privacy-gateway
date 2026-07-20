"""VehicleRegistrationDomain: round trip for both schemes (varying
segment lengths), literal 'BH' preserved for the BH-series scheme,
format validity via the existing detector as oracle."""

import pytest

from src.core.exceptions import SurrogateDomainError
from src.detect.tier1.vehicle_registration import VehicleRegistrationDetector
from src.surrogate.domains.vehicle_registration import VehicleRegistrationDomain

_KEY = b"k" * 32


@pytest.mark.parametrize(
    "value",
    [
        "KA01AB1234",  # standard state-code, 2-digit district, 2-letter series
        "DL8CAF5678",  # 1-digit district, 3-letter series
        "23BH1234AB",  # BH-series, 2-letter suffix
    ],
)
def test_decrypt_of_encrypt_returns_the_original_value(value: str) -> None:
    domain = VehicleRegistrationDomain()

    surrogate = domain.encrypt(value, _KEY)

    assert domain.decrypt(surrogate, _KEY) == value


@pytest.mark.parametrize(
    "value",
    ["KA01AB1234", "DL8CAF5678", "23BH1234AB"],
)
def test_surrogate_preserves_length_and_is_still_detected(value: str) -> None:
    domain = VehicleRegistrationDomain()
    surrogate = domain.encrypt(value, _KEY)

    assert len(surrogate) == len(value)
    spans = VehicleRegistrationDetector().detect(surrogate)

    assert len(spans) == 1
    assert spans[0].start == 0 and spans[0].end == len(surrogate)


def test_bh_series_literal_is_preserved() -> None:
    domain = VehicleRegistrationDomain()

    surrogate = domain.encrypt("23BH1234AB", _KEY)

    assert surrogate[2:4] == "BH"


def test_round_trips_with_a_single_letter_bh_suffix() -> None:
    domain = VehicleRegistrationDomain()
    value = "23BH1234A"

    surrogate = domain.encrypt(value, _KEY)

    assert domain.decrypt(surrogate, _KEY) == value
    assert len(surrogate) == len(value)


def test_rejects_value_matching_neither_scheme() -> None:
    domain = VehicleRegistrationDomain()

    with pytest.raises(SurrogateDomainError, match="neither"):
        domain.encrypt("KA01ABCD1234", _KEY)
