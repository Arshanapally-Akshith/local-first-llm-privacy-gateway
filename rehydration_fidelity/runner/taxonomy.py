"""The rehydration-fidelity taxonomy: the seven forms BUILD.md's Phase
3 section names a model's response might return a name surrogate in —
exact, decorated, case-shifted, partial, abbreviated, transliterated,
reasoned-about.

Each category is a deterministic transform of a *surrogate* (never the
real value — a model returning any of these forms never had the real
value to begin with; it only ever saw the surrogate). A category's
transform decides what "the model echoed the surrogate back this way"
looks like; the runner (`run.py`) is what decides whether that form was
successfully rehydrated.

This module makes no claim about which categories *should* round-trip —
that is exactly what the harness measures rather than assumes
(BUILD.md: "Measure, don't fix").
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

SAMPLE_REAL_NAMES: Final[tuple[str, ...]] = (
    "Ramesh Kumar",
    "Suresh Iyer",
    "Priya Nair",
    "Lakshmi Narayanan",
    "Fatima Begum",
    "Anil Verma",
    "Deepa Krishnan",
    "Imran Sheikh",
)
"""Synthetic stand-ins for real values a (not-yet-built, Phase 4)
PERSON detector would find — chosen to be generic, common-shape Indian
names with no connection to any actual identifiable person (CLAUDE.md:
"Synthetic PII only in this repo"). Each is a real *value*, distinct
from `src/session/names.py`'s `DEFAULT_NAME_CANDIDATES`, which is the
*surrogate* pool a real value gets allocated into — conflating the two
lists would make it harder to tell, at a glance, which name in this
harness's output is playing which role.
"""

_TRANSLITERATION_STAND_IN: Final[dict[str, str]] = {
    "a": "अ", "b": "ब", "c": "क", "d": "द", "e": "ए", "f": "फ", "g": "ग",
    "h": "ह", "i": "इ", "j": "ज", "k": "क", "l": "ल", "m": "म", "n": "न",
    "o": "ओ", "p": "प", "q": "क", "r": "र", "s": "स", "t": "त", "u": "उ",
    "v": "व", "w": "व", "x": "क्ष", "y": "य", "z": "ज़",
}  # fmt: skip
"""A crude, per-letter stand-in for real transliteration — not a
linguistically accurate Devanagari transliteration of anything, and not
meant to be one. This project has no transliteration engine or
linguistic data (building one is out of scope for a Phase 3 harness);
what this table needs to provide is only the *property* the
"transliterated" category exists to test — text that shares no
substring with the Latin surrogate it was derived from, so the
harness's exact-match rehydration has something honest to fail against.
Non-letter characters (spaces) pass through unchanged."""


def _transliterated(surrogate: str) -> str:
    return "".join(_TRANSLITERATION_STAND_IN.get(char.lower(), char) for char in surrogate)


def _abbreviated(surrogate: str) -> str:
    """`Arjun Reddy` -> `A. Reddy`. Assumes a "First Last" shape, true
    of every entry in `DEFAULT_NAME_CANDIDATES` today."""
    first, *_rest, last = surrogate.split(" ")
    return f"{first[0]}. {last}"


def _partial(surrogate: str) -> str:
    """`Arjun Reddy` -> `Arjun` — first token only."""
    return surrogate.split(" ")[0]


def _reasoned_about(surrogate: str) -> str:
    """Describes a property of the surrogate without ever repeating it
    verbatim — the case BUILD.md's own example ("the name starts with
    A") is naming: the model is reasoning *about* the value it was
    given, not returning it."""
    return f"The name starts with the letter {surrogate[0]}."


@dataclass(frozen=True, slots=True)
class TaxonomyCategory:
    name: str
    description: str
    transform: Callable[[str], str]
    """`(surrogate) -> the form a model might echo it back in`."""


TAXONOMY: Final[tuple[TaxonomyCategory, ...]] = (
    TaxonomyCategory("exact", "returned verbatim", lambda surrogate: surrogate),
    TaxonomyCategory(
        "decorated", "wrapped in markdown emphasis", lambda surrogate: f"**{surrogate}**"
    ),
    TaxonomyCategory("case_shifted", "returned in a different case", str.upper),
    TaxonomyCategory("partial", "first name only", _partial),
    TaxonomyCategory("abbreviated", "initial + last name", _abbreviated),
    TaxonomyCategory("transliterated", "rendered in a different script", _transliterated),
    TaxonomyCategory("reasoned_about", "described, not repeated", _reasoned_about),
)
"""One entry per BUILD.md Phase 3 category, in the order BUILD.md lists
them. `run.py` iterates this tuple — adding a category is adding one
entry here, not touching the runner."""
