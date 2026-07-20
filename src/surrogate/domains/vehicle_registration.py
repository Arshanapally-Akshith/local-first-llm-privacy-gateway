"""Indian vehicle registration surrogate domain.

Unlike PAN/IFSC, a matched value's exact segment lengths vary (the
state-code scheme's district code is 1-2 digits, its series is 1-3
letters; the BH-series suffix is 1-2 letters) — `VehicleRegistrationDetector`
already accepts both shapes without pinning them to one length. This
domain re-parses the matched value to recover its actual segment
boundaries before combining its free positions, rather than assuming
one fixed layout the way PAN/IFSC can.

Both schemes' combined free-position domains clear NIST's recommended
minimum comfortably even at their smallest observed length (state-code:
`26**4 * 10**6` at minimum: `456,976 * 1,000,000`; BH-series: at
minimum `10**6 * 26` — the digit positions alone already clear it), so
neither needs the "combine everything, even across letter/digit types"
justification PAN's 4-digit segment specifically needed.
"""

import re
from collections.abc import Callable
from typing import Final

from src.core.exceptions import SurrogateDomainError
from src.core.types import EntityType
from src.surrogate import mixed_radix_ff1

_RebuildFn = Callable[[list[int]], str]

_TWEAK: Final[bytes] = b"VEHICLE_REG"

_STATE_CODE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(?P<state>[A-Z]{2})(?P<district>\d{1,2})(?P<series>[A-Z]{1,3})(?P<number>\d{4})$"
)
_BH_SERIES_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(?P<year>\d{2})BH(?P<number>\d{4})(?P<suffix>[A-Z]{1,2})$"
)


class VehicleRegistrationDomain:
    entity_type: EntityType = "VEHICLE_REG"

    def encrypt(self, value: str, key: bytes) -> str:
        shape = _parse(value)
        permuted = mixed_radix_ff1.encrypt_combined(key, _TWEAK, shape.symbols, shape.radixes)
        return shape.rebuild(permuted)

    def decrypt(self, surrogate: str, key: bytes) -> str:
        shape = _parse(surrogate)
        original = mixed_radix_ff1.decrypt_combined(key, _TWEAK, shape.symbols, shape.radixes)
        return shape.rebuild(original)


class _ParsedShape:
    """The free-position symbols/radixes for one matched value, plus
    enough to reassemble a permuted symbol list back into the same
    textual shape — scheme-specific, built fresh per value since
    segment lengths vary."""

    def __init__(self, symbols: list[int], radixes: list[int], rebuild_fn: "_RebuildFn") -> None:
        self.symbols = symbols
        self.radixes = radixes
        self._rebuild_fn = rebuild_fn

    def rebuild(self, symbols: list[int]) -> str:
        return self._rebuild_fn(symbols)


def _parse(value: str) -> _ParsedShape:
    state_match = _STATE_CODE_PATTERN.match(value)
    if state_match:
        return _parse_state_code(state_match)
    bh_match = _BH_SERIES_PATTERN.match(value)
    if bh_match:
        return _parse_bh_series(bh_match)
    raise SurrogateDomainError(
        "VehicleRegistrationDomain value matched neither the state-code nor BH-series shape"
    )


def _parse_state_code(match: re.Match[str]) -> _ParsedShape:
    state, district, series, number = (
        match["state"],
        match["district"],
        match["series"],
        match["number"],
    )
    symbols = (
        [ord(c) - ord("A") for c in state]
        + [int(c) for c in district]
        + [ord(c) - ord("A") for c in series]
        + [int(c) for c in number]
    )
    radixes = [26] * len(state) + [10] * len(district) + [26] * len(series) + [10] * len(number)

    def rebuild(symbols: list[int]) -> str:
        i = 0
        out_state = "".join(chr(ord("A") + s) for s in symbols[i : i + len(state)])
        i += len(state)
        out_district = "".join(str(s) for s in symbols[i : i + len(district)])
        i += len(district)
        out_series = "".join(chr(ord("A") + s) for s in symbols[i : i + len(series)])
        i += len(series)
        out_number = "".join(str(s) for s in symbols[i : i + len(number)])
        return out_state + out_district + out_series + out_number

    return _ParsedShape(symbols, radixes, rebuild)


def _parse_bh_series(match: re.Match[str]) -> _ParsedShape:
    year, number, suffix = match["year"], match["number"], match["suffix"]
    symbols = (
        [int(c) for c in year] + [int(c) for c in number] + [ord(c) - ord("A") for c in suffix]
    )
    radixes = [10] * len(year) + [10] * len(number) + [26] * len(suffix)

    def rebuild(symbols: list[int]) -> str:
        i = 0
        out_year = "".join(str(s) for s in symbols[i : i + len(year)])
        i += len(year)
        out_number = "".join(str(s) for s in symbols[i : i + len(number)])
        i += len(number)
        out_suffix = "".join(chr(ord("A") + s) for s in symbols[i : i + len(suffix)])
        return out_year + "BH" + out_number + out_suffix

    return _ParsedShape(symbols, radixes, rebuild)
