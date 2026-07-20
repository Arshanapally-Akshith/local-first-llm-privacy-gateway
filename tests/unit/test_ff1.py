"""ff1.py against all nine of NIST's own published FF1 sample vectors
(AES-128/192/256 x radix 10/36 x empty/non-empty tweak) —
https://csrc.nist.gov/csrc/media/projects/cryptographic-standards-and-guidelines/documents/examples/ff1samples.pdf

Every vector's key, radix, tweak, plaintext, and ciphertext are
reproduced exactly as published; nothing here is derived from memory
of what FF1 "should" produce.
"""

import pytest

from src.core.exceptions import SurrogateDomainError
from src.surrogate.ff1 import ff1_decrypt, ff1_encrypt

_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"

_KEY_128 = bytes.fromhex("2B7E151628AED2A6ABF7158809CF4F3C")
_KEY_192 = bytes.fromhex("2B7E151628AED2A6ABF7158809CF4F3CEF4359D8D580AA4F")
_KEY_256 = bytes.fromhex("2B7E151628AED2A6ABF7158809CF4F3CEF4359D8D580AA4F7F036D6F04FC6A94")

_TWEAK_EMPTY = b""
_TWEAK_10 = bytes.fromhex("39383736353433323130")
_TWEAK_11 = bytes.fromhex("3737373770717273373737")


def _digits(text: str) -> list[int]:
    return [_ALPHABET.index(c) for c in text]


def _text(digits: list[int]) -> str:
    return "".join(_ALPHABET[d] for d in digits)


@pytest.mark.parametrize(
    "key,tweak,radix,plaintext,expected_ciphertext",
    [
        (_KEY_128, _TWEAK_EMPTY, 10, "0123456789", "2433477484"),
        (_KEY_128, _TWEAK_10, 10, "0123456789", "6124200773"),
        (_KEY_128, _TWEAK_11, 36, "0123456789abcdefghi", "a9tv40mll9kdu509eum"),
        (_KEY_192, _TWEAK_EMPTY, 10, "0123456789", "2830668132"),
        (_KEY_192, _TWEAK_10, 10, "0123456789", "2496655549"),
        (_KEY_192, _TWEAK_11, 36, "0123456789abcdefghi", "xbj3kv35jrawxv32ysr"),
        (_KEY_256, _TWEAK_EMPTY, 10, "0123456789", "6657667009"),
        (_KEY_256, _TWEAK_10, 10, "0123456789", "1001623463"),
        (_KEY_256, _TWEAK_11, 36, "0123456789abcdefghi", "xs8a0azh2avyalyzuwd"),
    ],
    ids=[f"nist-sample-{i}" for i in range(1, 10)],
)
def test_encrypt_matches_nist_sample_vector(
    key: bytes, tweak: bytes, radix: int, plaintext: str, expected_ciphertext: str
) -> None:
    result = ff1_encrypt(key, tweak, radix, _digits(plaintext))

    assert _text(result) == expected_ciphertext


@pytest.mark.parametrize(
    "key,tweak,radix,plaintext,expected_ciphertext",
    [
        (_KEY_128, _TWEAK_EMPTY, 10, "0123456789", "2433477484"),
        (_KEY_128, _TWEAK_10, 10, "0123456789", "6124200773"),
        (_KEY_128, _TWEAK_11, 36, "0123456789abcdefghi", "a9tv40mll9kdu509eum"),
        (_KEY_192, _TWEAK_EMPTY, 10, "0123456789", "2830668132"),
        (_KEY_192, _TWEAK_10, 10, "0123456789", "2496655549"),
        (_KEY_192, _TWEAK_11, 36, "0123456789abcdefghi", "xbj3kv35jrawxv32ysr"),
        (_KEY_256, _TWEAK_EMPTY, 10, "0123456789", "6657667009"),
        (_KEY_256, _TWEAK_10, 10, "0123456789", "1001623463"),
        (_KEY_256, _TWEAK_11, 36, "0123456789abcdefghi", "xs8a0azh2avyalyzuwd"),
    ],
    ids=[f"nist-sample-{i}" for i in range(1, 10)],
)
def test_decrypt_matches_nist_sample_vector(
    key: bytes, tweak: bytes, radix: int, plaintext: str, expected_ciphertext: str
) -> None:
    result = ff1_decrypt(key, tweak, radix, _digits(expected_ciphertext))

    assert _text(result) == plaintext


def test_decrypt_of_encrypt_round_trips_for_asymmetric_length() -> None:
    # n=19, u=9, v=10 (sample 3's shape) is the one case in the NIST
    # vectors where the two Feistel halves differ in length.
    digits = _digits("0123456789abcdefghi")

    encrypted = ff1_encrypt(_KEY_128, _TWEAK_11, 36, digits)
    decrypted = ff1_decrypt(_KEY_128, _TWEAK_11, 36, encrypted)

    assert decrypted == digits


def test_rejects_digit_list_shorter_than_minimum() -> None:
    with pytest.raises(SurrogateDomainError, match="below the minimum"):
        ff1_encrypt(_KEY_128, _TWEAK_EMPTY, 10, [5])


def test_rejects_radix_outside_supported_range() -> None:
    with pytest.raises(SurrogateDomainError, match="radix"):
        ff1_encrypt(_KEY_128, _TWEAK_EMPTY, 1, [0, 1, 2])
