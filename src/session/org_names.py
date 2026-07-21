"""The candidate list for `ORG` name-surrogate allocation (Phase 4
Task 5) — the same generation approach as `src/session/names.py`, a
different pair of seed pools.

A root-word pool and a business-suffix pool (~70 entries each) combine
into "Root Suffix" pairings (e.g. "Bharat Textiles", "Zenith
Logistics"). Deliberately generic/mythological/geographic root words,
not real company names: using an actual, identifiable brand (a real
bank, a real conglomerate) as a *surrogate* candidate would be a far
sharper version of the same residual this project already discloses for
Aadhaar surrogates coinciding with an issuable number pattern — except
here it would be a guaranteed, obvious collision with a specific real
entity rather than a low-probability shape coincidence, which is a
materially worse property for something explicitly meant to stand in
for *someone else's* data.
"""

from typing import Final

_ORG_ROOTS: Final[tuple[str, ...]] = (
    "Bharat", "Shree", "National", "Sunrise", "Deccan", "Ganga", "Nilgiri", "Himalaya",
    "Ashoka", "Vikram", "Suraj", "Continental", "Universal", "Global", "Prime", "Apex",
    "Pioneer", "Metro", "Capital", "Century", "Diamond", "Emerald", "Golden", "Silver",
    "Royal", "Imperial", "Classic", "Modern", "United", "Allied", "Standard", "Zenith",
    "Orbit", "Skyline", "Horizon", "Summit", "Everest", "Ganges", "Indus", "Krishna",
    "Godavari", "Narmada", "Konark", "Vijay", "Jai", "Om", "Shakti", "Surya",
    "Chandra", "Vayu", "Agni", "Prithvi", "Akash", "Vasundhara", "Bhoomi", "Sagar",
    "Meru", "Kailash", "Nandi", "Garuda", "Lotus", "Peacock", "Tiger", "Falcon",
    "Eagle", "Comet", "Nova", "Vertex", "Crest", "Crown",
)
"""70 root words — geographic/mythological/generic-descriptive only, no
real company or brand name (see module docstring)."""

_ORG_SUFFIXES: Final[tuple[str, ...]] = (
    "Textiles", "Industries", "Enterprises", "Technologies", "Traders", "Exports", "Solutions",
    "Logistics", "Constructions", "Chemicals", "Pharmaceuticals", "Electronics", "Motors", "Foods",
    "Agro", "Fabrics", "Garments", "Plastics", "Steel", "Cement", "Power", "Energy",
    "Infrastructure", "Realty", "Properties", "Developers", "Builders", "Consultants", "Associates",
    "Ventures", "Holdings", "Capital", "Finance", "Investments", "Insurance", "Retail",
    "Distributors", "Suppliers", "Manufacturing", "Engineering", "Automation", "Systems", "Networks",
    "Communications", "Media", "Publications", "Studios", "Productions", "Entertainment",
    "Hospitality", "Resorts", "Hotels", "Travels", "Tours", "Shipping", "Freight", "Cargo",
    "Warehousing", "Packaging", "Printing", "Publishing", "Fashions", "Apparels", "Leathers",
    "Ceramics", "Glassware", "Polymers", "Refineries", "Minerals", "Agencies",
)
"""70 generic business-entity suffixes, spanning a broad range of
sectors so no single industry dominates the surrogate distribution."""


def _generate_org_candidates() -> tuple[str, ...]:
    return tuple(f"{root} {suffix}" for root in _ORG_ROOTS for suffix in _ORG_SUFFIXES)


DEFAULT_ORG_CANDIDATES: Final[tuple[str, ...]] = _generate_org_candidates()
"""Every `_ORG_ROOTS` x `_ORG_SUFFIXES` combination — 4,900 candidates,
the same order of magnitude as `names.py`'s ~5,000, for the same
collision-math reasoning (ARCHITECTURE.md)."""
