"""Synthetic, structurally-valid entity value generation — one function
per `EntityType`, dispatched by `generate_value()`.

Reuse, not reimplementation (CLAUDE.md: "no duplicated logic" — this
module's own reason to exist is to avoid the alternative, a second
Verhoeff/Luhn/PAN-category implementation measuring itself instead of
the real detectors):

- AADHAAR / CARD: `src/detect/tier1/checksum.py`'s
  `verhoeff_generate_check_digit()` / `luhn_generate_check_digit()` —
  the exact functions that module's own docstring names this generator
  as the intended second caller of, alongside the Phase 2 FF1 engine.
- PAN: `src/detect/tier1/pan.py::PAN_CATEGORY_LETTERS` — the same
  documented Income Tax Department category-code set `PanDetector`
  validates against.
- IFSC / UPI / VEHICLE_REG / EMAIL / PHONE: no checksum exists for
  these (see each detector's own docstring); values are built directly
  from the same structural rule each detector's candidate pattern
  encodes (bank-code + literal `0` + branch code; VPA local-part +
  no-dot PSP handle; state-code/RTO/series/number; local + dot-TLD
  domain; leading-digit-6-9 mobile number). There is no separate
  algorithm to duplicate for these types — the "logic" is the shape
  itself, already stated once in each detector module.
- PERSON / ORG / ADDRESS: `src/session/candidates.py::get_candidates()`
  — the same finite pools the gateway's own name allocator draws
  surrogates from. Reusing them here means the benchmark's gold values
  are drawn from the identical "no real person, no real company, no
  single uniquely-identifying real street" pool the gateway's own
  privacy reasoning already applies (`docs/DECISIONS.md`, Phase 4 Task
  5) — appropriate for gold *values* too, since BUILD.md constraint #6
  requires all benchmark PII to be synthetic, not just structured PII.

Every generator takes an injected `random.Random`, never the global
`random` module (CLAUDE.md: "datetime.now() or random.choice() called
inline in domain code is a test you cannot write" — determinism here is
not a nice-to-have, it is a stated requirement of this task).
Correctness (offsets, checksum/structural validity) is proved by the
test suite driving the real Tier-1 detectors and `get_candidates()`
against this module's output — not asserted inline here, to keep
generation and validation as separate concerns.
"""

import random
import string
from collections.abc import Callable
from typing import Final

from src.core.types import EntityType, Offset, Span
from src.detect import precedence
from src.detect.registry import get_tier1_detectors
from src.detect.tier1.checksum import luhn_generate_check_digit, verhoeff_generate_check_digit
from src.detect.tier1.pan import PAN_CATEGORY_LETTERS
from src.session.candidates import get_candidates

_PAN_CATEGORY_LETTERS_SORTED: Final[tuple[str, ...]] = tuple(sorted(PAN_CATEGORY_LETTERS))
"""Sorted once, and always chosen from in this order: a `frozenset`'s
own iteration order is not guaranteed stable across processes (Python's
per-process string-hash randomization), and this generator's
determinism requirement (`rng.choice` over a fixed sequence) needs an
order that never silently changes underneath it."""

_STATE_CODES: Final[tuple[str, ...]] = (
    "KA", "MH", "DL", "TN", "AP", "TS", "WB", "GJ", "RJ", "UP",
)
"""A handful of well-known Indian state/UT vehicle-registration codes,
for carrier-sentence plausibility only. Deliberately not an attempt at
an exhaustive, authoritative RTO code table — `vehicle_registration.py`
itself declines to whitelist codes at all, for exactly the reason that
list "is not short, evolves, and reconstructing it from general
knowledge without a citable source would be... unverified-claim-
dressed-as-fact." No such table is needed here either:
`VehicleRegistrationDetector` never checks the 2-letter prefix against
any whitelist, so an implausible or even fictitious code has zero
correctness consequence — only realism, and these ten are common enough
not to look synthetic in a carrier sentence."""

_PSP_HANDLES: Final[tuple[str, ...]] = (
    "oksbi", "okhdfcbank", "okicici", "okaxis", "ybl", "ibl", "paytm", "upi",
)
"""Common NPCI-affiliated UPI handle suffixes — publicly documented PSP
handles, not fabricated. All-lowercase-letter, matching
`UpiDetector`'s PSP-handle grammar (`[A-Za-z][A-Za-z0-9]{1,64}`, no
dot) by construction."""

_EMAIL_DOMAINS: Final[tuple[str, ...]] = (
    "example.com", "example.net", "example.org", "example.edu",
)
"""RFC 2606's reserved "example" second-level domains — guaranteed
never to resolve to a real registrant, the email-address equivalent of
`org_names.py`'s refusal to use a real company name as a surrogate
candidate. Chosen for the same reason: a synthetic email that happens
to be someone's *real* address is a materially worse residual than one
that provably cannot be."""


def _generate_aadhaar(rng: random.Random) -> str:
    """A Verhoeff-valid, UIDAI-reserved-range Aadhaar (BUILD.md
    constraint #6: benchmark Aadhaar values must be Verhoeff-valid
    *and* drawn from UIDAI's documented `9999`-prefixed test-UID block
    — see `docs/DECISIONS.md`, 2026-07-20). The 11-digit payload is
    fixed to start `9999` (the documented reserved prefix) with 7 free
    digits; the 12th digit is the real Verhoeff check digit for that
    payload, computed by the same function the FF1 surrogate engine
    uses, not reimplemented.

    Unlike the FF1 *surrogate* domain (which was proven unable to
    guarantee reserved-range membership for arbitrary real inputs, see
    `docs/DECISIONS.md`, 2026-07-20 and 2026-07-22 supersession-adjacent
    entries), this generator has no such constraint to satisfy: it is
    free to *choose* every gold Aadhaar from the reserved block
    directly, since nothing here needs to invert an arbitrary
    caller-supplied real value.
    """
    payload = "9999" + "".join(str(rng.randint(0, 9)) for _ in range(7))
    return payload + verhoeff_generate_check_digit(payload)


def _generate_card(rng: random.Random) -> str:
    """A 16-digit, Luhn-valid synthetic payment card number. Leading
    digit fixed to `4` (Visa-shaped, the most common test-card
    convention) purely for carrier-sentence plausibility;
    `CardDetector` has no issuer-prefix check, so this choice has no
    effect on detectability."""
    payload = "4" + "".join(str(rng.randint(0, 9)) for _ in range(14))
    return payload + luhn_generate_check_digit(payload)


def _generate_pan(rng: random.Random) -> str:
    """A structurally-valid PAN: 5 letters (4th = a real Income Tax
    Department category code), 4 digits, 1 letter — the exact shape
    `PanDetector` requires, built from its own documented category-code
    set rather than a duplicate one."""
    first_three = "".join(rng.choice(string.ascii_uppercase) for _ in range(3))
    category_letter = rng.choice(_PAN_CATEGORY_LETTERS_SORTED)
    fifth_letter = rng.choice(string.ascii_uppercase)
    digits = "".join(str(rng.randint(0, 9)) for _ in range(4))
    last_letter = rng.choice(string.ascii_uppercase)
    return f"{first_three}{category_letter}{fifth_letter}{digits}{last_letter}"


def _generate_ifsc(rng: random.Random) -> str:
    """A structurally-valid IFSC: 4-letter bank code, the reserved
    literal `0`, 6-character alphanumeric branch code — `IfscDetector`'s
    exact shape."""
    bank_code = "".join(rng.choice(string.ascii_uppercase) for _ in range(4))
    branch_code = "".join(
        rng.choice(string.ascii_uppercase + string.digits) for _ in range(6)
    )
    return f"{bank_code}0{branch_code}"


def _generate_upi(rng: random.Random) -> str:
    """A structurally-valid UPI VPA: an alphanumeric local part and a
    dot-free PSP handle — `UpiDetector`'s exact shape, and specifically
    *not* `EmailDetector`'s (no dot ever appears after `@`)."""
    local_length = rng.randint(6, 12)
    local_part = "".join(
        rng.choice(string.ascii_lowercase + string.digits) for _ in range(local_length)
    )
    handle = rng.choice(_PSP_HANDLES)
    return f"{local_part}@{handle}"


def _generate_vehicle_registration(rng: random.Random) -> str:
    """A structurally-valid, state-code-scheme vehicle registration
    mark: 2-letter state code, 2-digit RTO code, 1-3 letter series,
    4-digit number — `VehicleRegistrationDetector`'s state-code-scheme
    shape (the BH-series alternative is not generated here; both are
    equally valid to the detector, and covering one exercises the same
    detection path)."""
    state = rng.choice(_STATE_CODES)
    rto = f"{rng.randint(1, 99):02d}"
    series_length = rng.randint(1, 3)
    series = "".join(rng.choice(string.ascii_uppercase) for _ in range(series_length))
    number = f"{rng.randint(0, 9999):04d}"
    return f"{state}{rto}{series}{number}"


def _generate_email(rng: random.Random) -> str:
    """A structurally-valid email at an RFC 2606 reserved domain —
    `EmailDetector`'s exact shape, guaranteed not to be anyone's real
    address by construction."""
    local_length = rng.randint(6, 10)
    local_part = "".join(rng.choice(string.ascii_lowercase) for _ in range(local_length))
    domain = rng.choice(_EMAIL_DOMAINS)
    return f"{local_part}@{domain}"


def _phone_candidate_wins_precedence(candidate: str) -> bool:
    """True iff the real cascade's own precedence rule
    (`src/detect/precedence.py`) would resolve `candidate`, run through
    every registered Tier-1 detector in isolation, to a single `PHONE`
    span covering the whole string.

    Reuses `precedence.resolve()` directly rather than re-deriving "does
    any other detector also match this string" by hand (e.g. "check
    length and registration order") — a hand-derived version of this
    exact rule is what produced the coincidental `PHONE`/`AADHAAR`/
    `CARD` collision this function exists to reject in the first place
    (`docs/DECISIONS.md`, 2026-07-22, "Phase 5 Task 7"). Calling the
    real function means this check can never itself drift out of sync
    with what the cascade actually does, including for collision shapes
    not enumerated by hand here.
    """
    spans_per_detector = [detector.detect(candidate) for detector in get_tier1_detectors()]
    resolved = precedence.resolve(spans_per_detector)
    return resolved == [
        Span(start=Offset(0), end=Offset(len(candidate)), entity_type="PHONE", tier=1)
    ]


def _generate_phone(rng: random.Random) -> str:
    """A structurally-valid Indian mobile number: leading digit 6-9,
    9 further digits, with an optional directly-attached `+91`/`91`/`0`
    prefix — `PhoneDetector`'s exact canonical-form shape.

    Regenerates (consuming more of `rng`'s stream, never reseeding it)
    until the candidate is confirmed, via the real cascade precedence
    rule, to actually resolve as `PHONE` — a `"91"`-prefixed value is
    exactly Aadhaar-shaped (12 digits) and, roughly 1 in 10 times, also
    happens to be Verhoeff- or Luhn-valid by pure chance, in which case
    the already-approved Tier-1 tie-break (registration order) would
    correctly attribute it to `AADHAAR`/`CARD` instead
    (`docs/DECISIONS.md`, 2026-07-22, "Phase 5 Task 7"). Rejecting such
    values here keeps determinism intact (the same seed always retries
    the same number of times and lands on the same final value) while
    ensuring every gold `PHONE` value in the dataset is unambiguously
    detectable as `PHONE` by construction, not merely `PHONE`-shaped.
    """
    while True:
        first_digit = rng.choice("6789")
        remaining_digits = "".join(str(rng.randint(0, 9)) for _ in range(9))
        prefix = rng.choice(("", "+91", "91", "0"))
        candidate = f"{prefix}{first_digit}{remaining_digits}"
        if _phone_candidate_wins_precedence(candidate):
            return candidate


def _generate_person(rng: random.Random) -> str:
    """A `PERSON` value drawn from the gateway's own finite,
    real-name-free candidate pool (`src/session/names.py`)."""
    return rng.choice(get_candidates("PERSON"))


def _generate_org(rng: random.Random) -> str:
    """An `ORG` value drawn from the gateway's own finite,
    real-company-free candidate pool (`src/session/org_names.py`)."""
    return rng.choice(get_candidates("ORG"))


def _generate_address(rng: random.Random) -> str:
    """An `ADDRESS` value drawn from the gateway's own finite,
    generic-street-name candidate pool (`src/session/addresses.py`)."""
    return rng.choice(get_candidates("ADDRESS"))


_GENERATORS: Final[dict[EntityType, Callable[[random.Random], str]]] = {
    "AADHAAR": _generate_aadhaar,
    "CARD": _generate_card,
    "PAN": _generate_pan,
    "IFSC": _generate_ifsc,
    "UPI": _generate_upi,
    "VEHICLE_REG": _generate_vehicle_registration,
    "EMAIL": _generate_email,
    "PHONE": _generate_phone,
    "PERSON": _generate_person,
    "ORG": _generate_org,
    "ADDRESS": _generate_address,
}


def generate_value(entity_type: EntityType, rng: random.Random) -> str:
    """Generate one synthetic value for `entity_type`, using `rng`
    (never the global `random` module — see module docstring).

    Raises:
        KeyError: `entity_type` has no registered generator. An
            internal precondition violation (every `EntityType` is
            registered above), not a request-time failure mode — same
            contract as `src/session/candidates.py::get_candidates()`.
    """
    return _GENERATORS[entity_type](rng)
