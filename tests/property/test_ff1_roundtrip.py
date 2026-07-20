"""Property test: decrypt(encrypt(x)) == x for every Tier-1 FF1 type
this phase implements — BUILD.md Phase 2 DoD: "FF1 round-trips ... for
every Tier-1 type, property-tested." Sampled examples don't prove an
invariant; this generates many across each domain's real input shape.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from src.detect.tier1.checksum import luhn_generate_check_digit, verhoeff_generate_check_digit
from src.surrogate.domains.aadhaar import AadhaarDomain
from src.surrogate.domains.card import CardDomain
from src.surrogate.domains.ifsc import IfscDomain
from src.surrogate.domains.pan import PanDomain
from src.surrogate.domains.phone import PhoneDomain
from src.surrogate.domains.vehicle_registration import VehicleRegistrationDomain

_KEY = b"k" * 32

_LETTER = st.characters(min_codepoint=ord("A"), max_codepoint=ord("Z"))
_ALNUM = st.one_of(_LETTER, st.characters(min_codepoint=ord("0"), max_codepoint=ord("9")))


@st.composite
def _aadhaar_values(draw: st.DrawFn) -> str:
    first = draw(st.integers(min_value=2, max_value=9))
    rest = draw(st.lists(st.integers(0, 9), min_size=10, max_size=10))
    payload = str(first) + "".join(str(d) for d in rest)
    return payload + verhoeff_generate_check_digit(payload)


@st.composite
def _card_values(draw: st.DrawFn) -> str:
    length = draw(st.integers(min_value=12, max_value=19))
    payload = "".join(str(draw(st.integers(0, 9))) for _ in range(length - 1))
    return payload + luhn_generate_check_digit(payload)


@st.composite
def _phone_values(draw: st.DrawFn) -> str:
    leading = draw(st.sampled_from("6789"))
    rest = "".join(str(draw(st.integers(0, 9))) for _ in range(9))
    core = leading + rest
    prefix = draw(st.sampled_from(["", "0", "91", "+91"]))
    return prefix + core


@st.composite
def _pan_values(draw: st.DrawFn) -> str:
    letters = "".join(draw(st.lists(_LETTER, min_size=3, max_size=3)))
    category = draw(st.sampled_from("PCHABGJLFT"))
    surname = draw(_LETTER)
    digits = "".join(str(draw(st.integers(0, 9))) for _ in range(4))
    check = draw(_LETTER)
    return letters + category + surname + digits + check


@st.composite
def _ifsc_values(draw: st.DrawFn) -> str:
    bank_code = "".join(draw(st.lists(_LETTER, min_size=4, max_size=4)))
    branch_code = "".join(draw(st.lists(_ALNUM, min_size=6, max_size=6)))
    return bank_code + "0" + branch_code


@st.composite
def _vehicle_registration_values(draw: st.DrawFn) -> str:
    if draw(st.booleans()):
        state = "".join(draw(st.lists(_LETTER, min_size=2, max_size=2)))
        district_len = draw(st.integers(1, 2))
        district = "".join(str(draw(st.integers(0, 9))) for _ in range(district_len))
        series_len = draw(st.integers(1, 3))
        series = "".join(draw(st.lists(_LETTER, min_size=series_len, max_size=series_len)))
        number = "".join(str(draw(st.integers(0, 9))) for _ in range(4))
        return state + district + series + number
    year = "".join(str(draw(st.integers(0, 9))) for _ in range(2))
    number = "".join(str(draw(st.integers(0, 9))) for _ in range(4))
    suffix_len = draw(st.integers(1, 2))
    suffix = "".join(draw(st.lists(_LETTER, min_size=suffix_len, max_size=suffix_len)))
    return year + "BH" + number + suffix


@settings(max_examples=100)
@given(_aadhaar_values())
def test_aadhaar_round_trips(value: str) -> None:
    domain = AadhaarDomain()
    assert domain.decrypt(domain.encrypt(value, _KEY), _KEY) == value


@settings(max_examples=100)
@given(_card_values())
def test_card_round_trips(value: str) -> None:
    domain = CardDomain()
    assert domain.decrypt(domain.encrypt(value, _KEY), _KEY) == value


@settings(max_examples=100)
@given(_phone_values())
def test_phone_round_trips(value: str) -> None:
    domain = PhoneDomain()
    assert domain.decrypt(domain.encrypt(value, _KEY), _KEY) == value


@settings(max_examples=100)
@given(_pan_values())
def test_pan_round_trips(value: str) -> None:
    domain = PanDomain()
    assert domain.decrypt(domain.encrypt(value, _KEY), _KEY) == value


@settings(max_examples=100)
@given(_ifsc_values())
def test_ifsc_round_trips(value: str) -> None:
    domain = IfscDomain()
    assert domain.decrypt(domain.encrypt(value, _KEY), _KEY) == value


@settings(max_examples=100)
@given(_vehicle_registration_values())
def test_vehicle_registration_round_trips(value: str) -> None:
    domain = VehicleRegistrationDomain()
    assert domain.decrypt(domain.encrypt(value, _KEY), _KEY) == value
