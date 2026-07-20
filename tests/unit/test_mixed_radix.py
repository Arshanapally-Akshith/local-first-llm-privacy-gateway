"""mixed_radix.py: `decode(encode(x, radixes), radixes) == x`, verified
entirely on its own terms — no FF1 involved anywhere in this file, per
this turn's instruction not to couple mixed-radix correctness to FF1
correctness.
"""

from hypothesis import given
from hypothesis import strategies as st

from src.surrogate.mixed_radix import decode, domain_size, encode


def test_encode_decode_round_trips_for_a_known_mixed_radix_shape() -> None:
    # PAN-shaped: 5 letter positions (radix 26) + 4 digit positions (radix 10).
    radixes = [26] * 5 + [10] * 4
    symbols = [0, 1, 2, 3, 4, 5, 6, 7, 8]

    value = encode(symbols, radixes)

    assert decode(value, radixes) == symbols


def test_encode_is_positional_most_significant_first() -> None:
    # [1, 0] in radix 10 is 10, not 1.
    assert encode([1, 0], [10, 10]) == 10
    assert encode([0, 1], [10, 10]) == 1


def test_domain_size_is_the_product_of_radixes() -> None:
    assert domain_size([26, 26, 10, 10]) == 26 * 26 * 10 * 10


def test_domain_size_of_uniform_radixes_is_a_power() -> None:
    assert domain_size([2] * 10) == 2**10


def test_uniform_radix_case_matches_ordinary_base_conversion() -> None:
    # A uniform radixes list is exactly the special case ff1's domain
    # modules use to hand a mixed-radix integer to FF1 as digits.
    value = 123456789
    radix, length = 16, 10

    digits = decode(value, [radix] * length)

    assert encode(digits, [radix] * length) == value


@given(
    st.lists(st.integers(min_value=2, max_value=36), min_size=1, max_size=8).flatmap(
        lambda radixes: st.tuples(
            st.just(radixes),
            st.tuples(*(st.integers(min_value=0, max_value=r - 1) for r in radixes)),
        )
    )
)
def test_round_trips_for_arbitrary_radix_shapes(data: tuple[list[int], tuple[int, ...]]) -> None:
    radixes, symbols = data

    value = encode(list(symbols), radixes)

    assert decode(value, radixes) == list(symbols)
    assert 0 <= value < domain_size(radixes)
