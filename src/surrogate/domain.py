"""SurrogateDomain — the seam every entity type's surrogate logic
implements.

Mirrors `src/detect/detector.py`'s `Detector` shape deliberately: a
`Protocol`, not an ABC, single responsibility (a domain converts a
value to/from a surrogate; it does not detect, does not resolve
precedence, does not touch the network), and every concrete domain is
substitutable behind this one protocol (CLAUDE.md SOLID: Liskov).

Ownership split (this turn's architectural adjustment): `ff1.py` is a
generic permutation with zero knowledge of any entity type; a domain
owns its alphabet, which positions are frozen, mixed-radix combination
where needed, and checksum repair; `engine.py` owns registry lookup
and orchestration. Domains call `ff1.py`/`mixed_radix.py` themselves —
see each concrete domain module for how.

Architectural invariant, preserved by every domain in this module:
**every surrogate domain is completely deterministic and stateless.**
Given the same `(entity_type, value, key)`, `encrypt` must always
produce the same surrogate, and `decrypt` must always invert it,
without consulting any external state. This is what makes Tier-1
surrogates need no session map at all — Phase 3's map is for names,
which are not deterministic functions of a key; FF1 domains are.
"""

from typing import Protocol

from src.core.types import EntityType


class SurrogateDomain(Protocol):
    entity_type: EntityType

    max_surrogate_length: int
    """The longest string this domain's `encrypt()` can ever produce.

    A fixed, cited property of the entity type's own regulatory format
    (e.g. Aadhaar is always 12 digits; a payment card is 12-19 digits
    per ISO/IEC 7812), not a measurement — each concrete domain states
    where its value comes from in its own module. Phase 3's response-
    path rehydration engine (`src/pipeline/rehydrate.py`) needs the
    longest surrogate across *every* registered domain to size the
    sliding window's lookahead margin correctly: too small, and a
    surrogate can be split across two released chunks before the
    engine ever sees it whole (BUILD.md, Phase 3: "Split-surrogate
    rehydration passes across 1/2/3/N chunk splits"). Exposed here,
    once, rather than duplicated as a second hand-copied constant
    elsewhere (CLAUDE.md: "no duplicated logic") — see
    `src/surrogate/registry.py::max_registered_surrogate_length()`.
    """

    def encrypt(self, value: str, key: bytes) -> str:
        """Return a format-preserving surrogate for `value`.

        Deterministic: the same `(value, key)` always yields the same
        surrogate — no randomness, no clock, no state read from
        anywhere but the two arguments.
        """
        ...

    def decrypt(self, surrogate: str, key: bytes) -> str:
        """Invert `encrypt`: `decrypt(encrypt(v, key), key) == v` for
        every `v` this domain accepts."""
        ...
