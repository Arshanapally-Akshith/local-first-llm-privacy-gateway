"""Verhoeff and Luhn checksum correctness, against published test vectors.

Verhoeff vectors are the standard ones from Verhoeff's own construction
(Wikipedia, "Verhoeff algorithm" — cross-checked, not invented here);
Luhn vectors are ISO/IEC 7812-1's own worked example plus the
industry-standard dummy test card number used by every major payment
sandbox (never a real, issuable card).
"""

import pytest

from src.detect.tier1.checksum import (
    luhn_generate_check_digit,
    luhn_is_valid,
    verhoeff_generate_check_digit,
    verhoeff_is_valid,
)


def test_verhoeff_accepts_known_valid_number() -> None:
    assert verhoeff_is_valid("2363") is True


def test_verhoeff_rejects_transposed_digits() -> None:
    # "2363" is valid; transposing the last two digits must invalidate it.
    assert verhoeff_is_valid("2336") is False


def test_verhoeff_rejects_single_digit_substitution() -> None:
    assert verhoeff_is_valid("2364") is False


def test_verhoeff_rejects_non_digit_input() -> None:
    assert verhoeff_is_valid("236A") is False
    assert verhoeff_is_valid("") is False


def test_verhoeff_generate_check_digit_matches_known_vector() -> None:
    assert verhoeff_generate_check_digit("236") == "3"


def test_verhoeff_generate_then_validate_round_trips() -> None:
    payload = "23456789012"
    check_digit = verhoeff_generate_check_digit(payload)

    assert verhoeff_is_valid(payload + check_digit) is True


def test_verhoeff_generate_check_digit_rejects_non_digit_payload() -> None:
    with pytest.raises(ValueError, match="non-digit payload"):
        verhoeff_generate_check_digit("23A")


def test_luhn_accepts_known_valid_number() -> None:
    assert luhn_is_valid("79927398713") is True


def test_luhn_accepts_industry_standard_test_card_number() -> None:
    # 4111111111111111 — the universal Visa test/sandbox card number
    # used by every major payment processor's docs; never a real,
    # issuable card.
    assert luhn_is_valid("4111111111111111") is True


def test_luhn_rejects_single_digit_substitution() -> None:
    assert luhn_is_valid("79927398710") is False
    assert luhn_is_valid("4111111111111112") is False


def test_luhn_rejects_non_digit_and_too_short_input() -> None:
    assert luhn_is_valid("7992739871A") is False
    assert luhn_is_valid("7") is False
    assert luhn_is_valid("") is False


def test_luhn_generate_check_digit_matches_known_vector() -> None:
    assert luhn_generate_check_digit("7992739871") == "3"


def test_luhn_generate_then_validate_round_trips() -> None:
    payload = "411111111111111"
    check_digit = luhn_generate_check_digit(payload)

    assert luhn_is_valid(payload + check_digit) is True


def test_luhn_generate_check_digit_rejects_non_digit_payload() -> None:
    with pytest.raises(ValueError, match="non-digit payload"):
        luhn_generate_check_digit("41A")
