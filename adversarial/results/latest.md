# Phase 6 Adversarial Suite Results

Commit: `e47a030a4cf7f4f048db1af7d51f63ee30809c3f`
Total cases: 42

> Scope: single-bypass attacks only. Every case below applies exactly one obfuscation technique. Combinations (e.g. base64 + zero-width, split-across-turns + homoglyph, or any other pairing of two classes in this suite) have not been measured and are out of scope for this phase — do not read a class's recall number as bounding performance against a combined attack.

Clean and adversarial recall are reported separately per class and are never averaged — the gap between them is the finding.

A case counts as *caught* only if all three hold: the captured upstream body is still valid JSON, the original sensitive value is absent from it, and something was actually substituted in its place (not merely deleted) — see `adversarial/cases/case_types.py::VerificationOutcome`.

| Bypass class | Clean recall | Adversarial recall | Entity types covered | Entity types omitted |
|---|---|---|---|---|
| base64_encoding | 1.00 (2/2) | 0.00 (0/2) | AADHAAR, CARD | ADDRESS, EMAIL, IFSC, ORG, PAN, PERSON, PHONE, UPI, VEHICLE_REG |
| homoglyphs | 1.00 (2/2) | 0.00 (0/2) | IFSC, PAN | AADHAAR, ADDRESS, CARD, EMAIL, ORG, PERSON, PHONE, UPI, VEHICLE_REG |
| number_words | 1.00 (3/3) | 0.00 (0/3) | AADHAAR, CARD, PHONE | ADDRESS, EMAIL, IFSC, ORG, PAN, PERSON, UPI, VEHICLE_REG |
| pii_in_code | 1.00 (2/2) | 0.00 (0/2) | AADHAAR, PAN | ADDRESS, CARD, EMAIL, IFSC, ORG, PERSON, PHONE, UPI, VEHICLE_REG |
| pii_in_json_key | 1.00 (2/2) | 0.00 (0/2) | AADHAAR, PHONE | ADDRESS, CARD, EMAIL, IFSC, ORG, PAN, PERSON, UPI, VEHICLE_REG |
| spaced_digits | 1.00 (3/3) | 0.00 (0/3) | AADHAAR, CARD, PHONE | ADDRESS, EMAIL, IFSC, ORG, PAN, PERSON, UPI, VEHICLE_REG |
| split_across_turns | 1.00 (2/2) | 0.00 (0/2) | AADHAAR, PHONE | ADDRESS, CARD, EMAIL, IFSC, ORG, PAN, PERSON, UPI, VEHICLE_REG |
| transliterated_names | 1.00 (2/2) | 1.00 (2/2) | PERSON | AADHAAR, ADDRESS, CARD, EMAIL, IFSC, ORG, PAN, PHONE, UPI, VEHICLE_REG |
| zero_width | 1.00 (3/3) | 0.00 (0/3) | AADHAAR, CARD, PAN | ADDRESS, EMAIL, IFSC, ORG, PERSON, PHONE, UPI, VEHICLE_REG |

Omission rationale for every class lives in that class's own module docstring (`adversarial/cases/<bypass_class>.py`), not only here.

## Bypasses that still work (19)

| Case | Entity type | Detail |
|---|---|---|
| base64_encoding-AADHAAR-adversarial | AADHAAR | prefix/suffix invariant held; sent value unchanged |
| base64_encoding-CARD-adversarial | CARD | prefix/suffix invariant held; sent value unchanged |
| homoglyphs-IFSC-adversarial | IFSC | prefix/suffix invariant held; sent value unchanged |
| homoglyphs-PAN-adversarial | PAN | prefix/suffix invariant held; sent value unchanged |
| number_words-AADHAAR-adversarial | AADHAAR | prefix/suffix invariant held; sent value unchanged |
| number_words-CARD-adversarial | CARD | prefix/suffix invariant held; sent value unchanged |
| number_words-PHONE-adversarial | PHONE | prefix/suffix invariant held; sent value unchanged |
| pii_in_code-AADHAAR-adversarial | AADHAAR | prefix/suffix invariant held; sent value unchanged |
| pii_in_code-PAN-adversarial | PAN | prefix/suffix invariant held; sent value unchanged |
| pii_in_json_key-AADHAAR-adversarial | AADHAAR | key_present=True (True means the JSON key crossed unmodified) |
| pii_in_json_key-PHONE-adversarial | PHONE | key_present=True (True means the JSON key crossed unmodified) |
| spaced_digits-AADHAAR-adversarial | AADHAAR | prefix/suffix invariant held; sent value unchanged |
| spaced_digits-CARD-adversarial | CARD | prefix/suffix invariant held; sent value unchanged |
| spaced_digits-PHONE-adversarial | PHONE | prefix/suffix invariant held; sent value unchanged |
| split_across_turns-AADHAAR-adversarial | AADHAAR | fragments_intact=True (True means both halves crossed unchanged, making the full value trivially reconstructable from the transcript) |
| split_across_turns-PHONE-adversarial | PHONE | fragments_intact=True (True means both halves crossed unchanged, making the full value trivially reconstructable from the transcript) |
| zero_width-AADHAAR-adversarial | AADHAAR | prefix/suffix invariant held; sent value unchanged |
| zero_width-CARD-adversarial | CARD | prefix/suffix invariant held; sent value unchanged |
| zero_width-PAN-adversarial | PAN | prefix/suffix invariant held; sent value unchanged |

## Prediction mismatches (2)

A mismatch means this suite's own predicted outcome (`AdversarialCase.expected_outcome`) did not match what was actually measured — reported here rather than silently corrected, per this project's own honesty standard.

| Case | Predicted | Actual caught | Detail |
|---|---|---|---|
| transliterated_names-0-adversarial | leaked | True | prefix/suffix invariant held; sent value replaced |
| transliterated_names-1-adversarial | leaked | True | prefix/suffix invariant held; sent value replaced |

## Blind red-team

Not part of this automated report by design — see `adversarial/results/redteam.md` for the manual exercise's template and recording format, and its own contents once a session has been run.

