"""Carrier sentences with `{ENTITY_TYPE}` slots — the "LLM generates
carrier sentences with slots" half of BUILD.md's slot-and-inject
methodology (`benchmarks/generate/__init__.py`'s module docstring
explains why this is static, authored content rather than a live API
call).

English (`"en"`) and Hindi/Telugu-English code-switched (`"hi_en"`)
varieties, per BUILD.md's Phase 5 bullet ("English +
Hinglish/Telugu-English code-switched"). The code-switched templates
are romanized (Latin script) throughout, not mixed-script
(Devanagari/Telugu characters) — a deliberate scope limit for this
first dataset, flagged in Task 2's completion report as a design point
worth revisiting, not a silent omission.

Every slot name must be a member of `src.core.types.ENTITY_TYPES`;
`tests/unit/test_benchmark_templates.py` scans every template for
*any* brace-delimited token (not just ones this module's own injector
would recognise) and asserts each one is a known entity type — a typo
like `{ADRESS}` would otherwise silently survive as literal template
text instead of becoming a gold span, which is exactly the kind of
quiet, undetected mislabeling this project's testing philosophy exists
to catch.

Two structural rules, also enforced by tests, keep injection
unambiguous:

- No template repeats the same entity type in two different slots
  (avoids two independently-sampled values for one type landing in one
  sentence, which adds no coverage value and only invites accidental
  substring collisions to reason about).
- No template ends immediately with `{UPI}` or `{EMAIL}` followed by a
  literal `.` with no separating character — `UpiDetector`'s and
  `EmailDetector`'s own boundary lookaheads specifically reject a
  trailing dot immediately after the token (see their module
  docstrings), so a generated value glued directly to a sentence-final
  period would silently fail to be detected in situ, corrupting the
  gold label's own validity. Every other entity type's `\\b`-based
  boundary tolerates a following period as an ordinary word boundary
  and has no equivalent hazard.
"""

from dataclasses import dataclass
from typing import Final

from benchmarks.generate.dataset_types import Language


@dataclass(frozen=True, slots=True)
class CarrierTemplate:
    template_id: str
    language: Language
    text: str


TEMPLATES: Final[tuple[CarrierTemplate, ...]] = (
    # -- English, single-slot --------------------------------------------
    CarrierTemplate("en-001", "en", "My Aadhaar number is {AADHAAR} and I need it verified urgently."),
    CarrierTemplate("en-002", "en", "Please update my PAN {PAN} in the company records."),
    CarrierTemplate("en-003", "en", "The beneficiary bank IFSC code is {IFSC} for the NEFT transfer."),
    CarrierTemplate("en-004", "en", "You can pay me directly at my UPI ID {UPI} for the refund."),
    CarrierTemplate(
        "en-005",
        "en",
        "The vehicle with registration number {VEHICLE_REG} was reported for over-speeding.",
    ),
    CarrierTemplate("en-006", "en", "My card number {CARD} was declined at checkout yesterday."),
    CarrierTemplate("en-007", "en", "Send the invoice to my email address {EMAIL} by end of day."),
    CarrierTemplate("en-008", "en", "Call me on {PHONE} once you have the delivery details."),
    CarrierTemplate("en-009", "en", "{PERSON} will be joining the onboarding call at 10 AM."),
    CarrierTemplate("en-010", "en", "This contract is between the client and {ORG} for the fiscal year."),
    CarrierTemplate("en-011", "en", "Please courier the documents to {ADDRESS} before Friday."),
    CarrierTemplate("en-018", "en", "My Aadhaar is {AADHAAR}."),
    CarrierTemplate("en-019", "en", "PAN no. {PAN}"),
    CarrierTemplate("en-020", "en", "Aadhaar: {AADHAAR}"),
    CarrierTemplate("en-021", "en", "UPI: {UPI}"),
    CarrierTemplate("en-026", "en", "Registration number {VEHICLE_REG} is flagged for renewal."),
    CarrierTemplate("en-027", "en", "Reach out to {ORG} directly for the procurement query."),
    CarrierTemplate("en-028", "en", "The new hire's mobile number on file is {PHONE}."),
    CarrierTemplate("en-029", "en", "{PERSON} has requested access to the shared drive."),
    CarrierTemplate("en-030", "en", "Refund processed to card {CARD} within three business days."),
    # -- English, multi-slot ----------------------------------------------
    CarrierTemplate(
        "en-012", "en", "For KYC purposes, share your Aadhaar {AADHAAR} and PAN {PAN} with the branch."
    ),
    CarrierTemplate(
        "en-013",
        "en",
        "Transfer the amount using IFSC {IFSC} to the UPI account {UPI} today.",
    ),
    CarrierTemplate("en-014", "en", "{PERSON} from {ORG} confirmed the meeting for next week."),
    CarrierTemplate(
        "en-015",
        "en",
        "The delivery for {PERSON} should go to {ADDRESS}, and you can reach them at {PHONE}.",
    ),
    CarrierTemplate(
        "en-016",
        "en",
        "Reported theft: vehicle {VEHICLE_REG} and card {CARD} were both flagged.",
    ),
    CarrierTemplate("en-017", "en", "Please email {EMAIL} and cc {PERSON} regarding the pending invoice."),
    CarrierTemplate(
        "en-022", "en", "Contact {PERSON} at {ORG} via {EMAIL} or {PHONE} for the interview."
    ),
    CarrierTemplate(
        "en-023",
        "en",
        "The refund was credited to card {CARD}; a copy of the receipt went to {EMAIL} today.",
    ),
    CarrierTemplate(
        "en-024",
        "en",
        "New employee {PERSON} has been assigned to the {ORG} team, residing at {ADDRESS}.",
    ),
    CarrierTemplate(
        "en-025",
        "en",
        "Vehicle {VEHICLE_REG} registered under {PERSON} needs a fitness certificate renewal.",
    ),
    CarrierTemplate(
        "en-031",
        "en",
        "{PERSON}'s Aadhaar {AADHAAR} was submitted along with the loan application.",
    ),
    CarrierTemplate(
        "en-032",
        "en",
        "Send the UPI payment to {UPI} and confirm with {PERSON} once it clears.",
    ),
    # -- Hindi-English / Telugu-English code-switched, romanized ----------
    CarrierTemplate(
        "hi-001", "hi_en", "Mera Aadhaar number {AADHAAR} hai, please isko verify kar dijiye."
    ),
    CarrierTemplate("hi-002", "hi_en", "Aapka PAN {PAN} humare records mein already register hai."),
    CarrierTemplate("hi-003", "hi_en", "Payment {UPI} pe bhej dena, thank you."),
    CarrierTemplate("hi-004", "hi_en", "Gaadi ka number {VEHICLE_REG} tha jo challan mein aaya hai."),
    CarrierTemplate("hi-005", "hi_en", "Mera card {CARD} se transaction kal fail ho gaya."),
    CarrierTemplate("hi-006", "hi_en", "Mujhe {EMAIL} pe invoice bhej dijiye, jaldi chahiye."),
    CarrierTemplate("hi-007", "hi_en", "{PERSON} ko {PHONE} par call kar lena, woh available hain."),
    CarrierTemplate("hi-008", "hi_en", "{ORG} ke saath contract is mahine renew karna hai."),
    CarrierTemplate("hi-009", "hi_en", "Courier {ADDRESS} pe bhej dijiye, {PERSON} wahi rehte hain."),
    CarrierTemplate(
        "hi-010", "hi_en", "IFSC code {IFSC} confirm kar dijiye branch se, transfer pending hai."
    ),
    CarrierTemplate(
        "hi-011",
        "hi_en",
        "Aadhaar {AADHAAR} aur PAN {PAN} dono submit karne honge KYC ke liye.",
    ),
    CarrierTemplate("hi-012", "hi_en", "{PERSON} garu {ORG} lo ee week join ayyaru."),
    CarrierTemplate(
        "hi-013", "hi_en", "Naa phone number {PHONE}, evaraina kavaali ante contact cheyandi."
    ),
    CarrierTemplate("hi-014", "hi_en", "{PERSON} address {ADDRESS} ki courier pampandi."),
    CarrierTemplate("hi-015", "hi_en", "UPI ID {UPI} ki paisalu pampandi, urgent undi."),
    CarrierTemplate(
        "hi-016", "hi_en", "Card number {CARD} tho transaction fail ayyindi, please check cheyandi."
    ),
    CarrierTemplate(
        "hi-017",
        "hi_en",
        "Vehicle {VEHICLE_REG} already register ayindi, records lo update cheyandi.",
    ),
    CarrierTemplate(
        "hi-018", "hi_en", "Email {EMAIL} ki details pamputunnanu, PAN {PAN} kuda unnadi."
    ),
    CarrierTemplate(
        "hi-019", "hi_en", "{ORG} lo naa Aadhaar {AADHAAR} already verify chesaru."
    ),
    CarrierTemplate(
        "hi-020",
        "hi_en",
        "{PERSON} ka Aadhaar {AADHAAR} aur phone {PHONE} dono form mein daal dijiye.",
    ),
)
"""Every declared carrier template. `TEMPLATES` is intentionally not a
`Final` typed as `tuple[CarrierTemplate, ...]` with implicit narrowing
skipped — mypy --strict infers the precise tuple length/element type
from the literal above regardless; `Final` is omitted only because
nothing here is ever meant to be reassigned dynamically and the literal
tuple already communicates that."""
