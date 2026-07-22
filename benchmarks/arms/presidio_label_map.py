"""The one, shared table translating Presidio's own entity labels into
this project's `EntityType` vocabulary — used by every arm that keeps
any of Presidio's stock recognizers (arm 1 in full; arm 2 for the types
it does not add a custom recognizer for).

Fixed once and applied identically everywhere a stock Presidio label is
consumed, for the same reason `docs/DECISIONS.md` (2026-07-22) fixed the
span-matching criterion before any arm existed: a mapping decided
per-arm, or revisited after seeing results, would let "which labels count
as which entity type" become an unaudited knob — precisely what that
entry's own reasoning about criterion-stability already argues against,
applied here to a different but equally load-bearing methodological
choice.

Only entity types this project actually reports on are mapped. A stock
Presidio label with no entry here (e.g. `LOCATION`, `IBAN_CODE`,
`CRYPTO`, `US_SSN` — entities Presidio detects that have no
correspondence in this project's own `EntityType` set) is deliberately
dropped by every arm that uses this table, not coerced into the nearest
type — a coerced mapping would be inventing evidence a baseline never
actually claimed.
"""

from typing import Final

from src.core.types import EntityType

PRESIDIO_LABEL_TO_ENTITY_TYPE: Final[dict[str, EntityType]] = {
    "CREDIT_CARD": "CARD",
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "PHONE",
    "PERSON": "PERSON",
}
"""Presidio's own default recognizer labels for the four entity types
this project's structured/PERSON vocabulary already overlaps with,
confirmed as Presidio's standard, long-documented default label names
for its built-in `CreditCardRecognizer`, `EmailRecognizer`,
`PhoneRecognizer`, and spaCy-backed `PERSON` NER output.

Presidio's exact *default-configuration* entity coverage beyond these
four (in particular, whether an `ORGANIZATION`-labeled span appears for
this project's `ORG` type, or a `LOCATION`-labeled span for `ADDRESS`,
under a fully vanilla `AnalyzerEngine()`) is verified empirically against
the real installed package, not assumed here — see
`tests/unit/test_presidio_stock_arm.py` and
`docs/DECISIONS.md`'s Phase 5 Task 4 entry for what was actually
observed. No entry for `ORG`/`ADDRESS` is added to this table unless
that verification found one worth trusting as a genuine default, stable
baseline signal rather than an artifact of one example sentence.
"""
