"""mixed_radix_ff1.py: the cycle-walking glue between mixed_radix and
ff1, tested at this module's own level — not through a full entity
domain — so a failure here points at the glue, not at PAN/IFSC/vehicle
registration's own position-mapping logic.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from src.surrogate.mixed_radix_ff1 import decrypt_combined, encrypt_combined

_KEY = b"k" * 32
_TWEAK = b"TEST"
_PAN_SHAPED_RADIXES = [26] * 5 + [10] * 4


def test_round_trips_for_a_pan_shaped_domain() -> None:
    symbols = [0, 1, 2, 3, 4, 5, 6, 7, 8]

    encrypted = encrypt_combined(_KEY, _TWEAK, symbols, _PAN_SHAPED_RADIXES)
    decrypted = decrypt_combined(_KEY, _TWEAK, encrypted, _PAN_SHAPED_RADIXES)

    assert decrypted == symbols


def test_encryption_actually_changes_the_value() -> None:
    symbols = [0, 1, 2, 3, 4, 5, 6, 7, 8]

    encrypted = encrypt_combined(_KEY, _TWEAK, symbols, _PAN_SHAPED_RADIXES)

    assert encrypted != symbols


def test_output_symbols_stay_within_their_own_radix() -> None:
    symbols = [25, 25, 25, 25, 25, 9, 9, 9, 9]  # max value at every position

    encrypted = encrypt_combined(_KEY, _TWEAK, symbols, _PAN_SHAPED_RADIXES)

    for symbol, radix in zip(encrypted, _PAN_SHAPED_RADIXES, strict=True):
        assert 0 <= symbol < radix


def test_different_tweaks_produce_different_surrogates() -> None:
    symbols = [0, 1, 2, 3, 4, 5, 6, 7, 8]

    a = encrypt_combined(_KEY, b"AAAA", symbols, _PAN_SHAPED_RADIXES)
    b = encrypt_combined(_KEY, b"BBBB", symbols, _PAN_SHAPED_RADIXES)

    assert a != b


@settings(max_examples=200)
@given(
    st.tuples(
        *([st.integers(0, 25)] * 5),
        *([st.integers(0, 9)] * 4),
    )
)
def test_round_trips_for_many_pan_shaped_values(symbols: tuple[int, ...]) -> None:
    encrypted = encrypt_combined(_KEY, _TWEAK, list(symbols), _PAN_SHAPED_RADIXES)
    decrypted = decrypt_combined(_KEY, _TWEAK, encrypted, _PAN_SHAPED_RADIXES)

    assert decrypted == list(symbols)


def test_round_trips_for_a_small_domain_needing_many_cycle_walk_steps() -> None:
    # radix 3, length 4 -> true_size=81; smallest covering power of two
    # is 2**7=128, a ~1.58x covering ratio -- exercises a domain where
    # a meaningful fraction of attempts land outside the true domain,
    # not just the near-1.0-ratio case PAN/IFSC/vehicle-reg see in
    # practice.
    radixes = [3, 3, 3, 3]
    symbols = [2, 2, 2, 2]

    encrypted = encrypt_combined(_KEY, _TWEAK, symbols, radixes)
    decrypted = decrypt_combined(_KEY, _TWEAK, encrypted, radixes)

    assert decrypted == symbols
    for symbol, radix in zip(encrypted, radixes, strict=True):
        assert 0 <= symbol < radix
