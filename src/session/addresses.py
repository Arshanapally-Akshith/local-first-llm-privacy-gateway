"""The candidate list for `ADDRESS` name-surrogate allocation (Phase 4
Task 5) — the same generation approach as `src/session/names.py` and
`org_names.py`, adapted for a three-part shape: a house number, a
street name, and a city/state.

Street names are deliberately generic patterns reused across hundreds
of real Indian cities (`Gandhi Road`, `Station Road`, `MG Road`, named
after national figures or describing a location type) rather than a
single, uniquely identifying real street — the same reasoning
`org_names.py` applies to avoiding real company names. City/state pairs
are necessarily real (India has a fixed, public set of cities and
states — this is no different from a benchmark using real city names as
carrier-sentence content), so the residual is the same kind
ARCHITECTURE.md already discloses for names: a generated address
*could* coincide with a real one, exactly as a generated name could
coincide with a real person's.
"""

from typing import Final

_STREET_NAMES: Final[tuple[str, ...]] = (
    "MG Road", "Station Road", "Gandhi Road", "Nehru Road", "Ring Road", "Park Street",
    "Church Street", "College Road", "Market Road", "Temple Street", "Mosque Road", "Civil Lines",
    "Model Town", "Sector Road", "Ashok Marg", "Rajpath", "Link Road", "Service Road",
    "Outer Ring Road", "Inner Ring Road", "Race Course Road", "Cantonment Road", "Old City Road",
    "New Town Road", "Industrial Area Road", "Housing Colony Road", "Green Park", "Lake View Road",
    "Hill Road", "River Side Road", "Canal Road", "Bridge Road", "Fort Road", "Palace Road",
    "Garden Road", "School Road", "Hospital Road", "Stadium Road", "Airport Road", "Highway Road",
    "Bypass Road", "Junction Road", "Cross Road", "Main Road", "East Street", "West Street",
    "North Avenue", "South Avenue", "First Cross", "Second Cross", "Third Cross", "Fourth Cross",
    "Fifth Cross", "First Main", "Second Main", "Third Main", "Vivekananda Road", "Tagore Road",
    "Bose Road", "Patel Road", "Shastri Road", "Subhash Road", "Tilak Road", "Azad Road",
    "Bhagat Singh Road", "Ambedkar Road", "Rajiv Gandhi Road", "Indira Gandhi Road",
    "Sardar Patel Road", "Lal Bahadur Shastri Road",
)
"""70 street-name patterns — generic location descriptions or names
shared by hundreds of real streets nationwide, never a single uniquely
identifying real address."""

_CITY_STATES: Final[tuple[str, ...]] = (
    "Bengaluru, Karnataka", "Chennai, Tamil Nadu", "Hyderabad, Telangana", "Mumbai, Maharashtra",
    "Pune, Maharashtra", "Delhi, Delhi", "Kolkata, West Bengal", "Ahmedabad, Gujarat",
    "Jaipur, Rajasthan", "Lucknow, Uttar Pradesh", "Kanpur, Uttar Pradesh", "Nagpur, Maharashtra",
    "Indore, Madhya Pradesh", "Bhopal, Madhya Pradesh", "Patna, Bihar", "Vadodara, Gujarat",
    "Surat, Gujarat", "Coimbatore, Tamil Nadu", "Kochi, Kerala", "Thiruvananthapuram, Kerala",
    "Visakhapatnam, Andhra Pradesh", "Vijayawada, Andhra Pradesh", "Nashik, Maharashtra",
    "Rajkot, Gujarat", "Varanasi, Uttar Pradesh", "Amritsar, Punjab", "Ludhiana, Punjab",
    "Chandigarh, Punjab", "Guwahati, Assam", "Bhubaneswar, Odisha", "Ranchi, Jharkhand",
    "Raipur, Chhattisgarh", "Dehradun, Uttarakhand", "Shimla, Himachal Pradesh",
    "Jodhpur, Rajasthan", "Udaipur, Rajasthan", "Mysuru, Karnataka", "Mangaluru, Karnataka",
    "Hubballi, Karnataka", "Madurai, Tamil Nadu", "Tiruchirappalli, Tamil Nadu", "Salem, Tamil Nadu",
    "Agra, Uttar Pradesh", "Meerut, Uttar Pradesh", "Allahabad, Uttar Pradesh",
    "Gwalior, Madhya Pradesh", "Jabalpur, Madhya Pradesh", "Aurangabad, Maharashtra",
    "Solapur, Maharashtra", "Thane, Maharashtra", "Faridabad, Haryana", "Gurugram, Haryana",
    "Rohtak, Haryana", "Panipat, Haryana", "Siliguri, West Bengal", "Durgapur, West Bengal",
    "Asansol, West Bengal", "Guntur, Andhra Pradesh", "Nellore, Andhra Pradesh",
    "Warangal, Telangana", "Nizamabad, Telangana", "Kollam, Kerala", "Thrissur, Kerala",
    "Kozhikode, Kerala", "Bikaner, Rajasthan", "Ajmer, Rajasthan", "Kota, Rajasthan",
    "Bareilly, Uttar Pradesh", "Moradabad, Uttar Pradesh", "Aligarh, Uttar Pradesh",
    "Jalandhar, Punjab", "Patiala, Punjab",
)
"""72 real "City, State" pairs. Real by necessity (a fixed, public set,
same as using real city names in benchmark carrier sentences) — the
synthetic part is the street name and house number around them."""


def _generate_address_candidates() -> tuple[str, ...]:
    """Every `_STREET_NAMES` x `_CITY_STATES` combination, each paired
    with a deterministic (not random) house number so the surrogate is
    address-*shaped* rather than a bare "Street, City" fragment.

    The number is derived from each pair's own position in the
    cartesian product, not `random` — this module has no RNG dependency
    and none is needed: house-number variety is cosmetic (the pairing
    of street and city is what guarantees every candidate is unique),
    so a fixed, reproducible formula is strictly simpler than injecting
    randomness for a property that isn't actually random.
    """
    candidates = []
    for street_index, street in enumerate(_STREET_NAMES):
        for city_index, city_state in enumerate(_CITY_STATES):
            house_number = ((street_index * len(_CITY_STATES) + city_index) % 900) + 1
            candidates.append(f"{house_number} {street}, {city_state}")
    return tuple(candidates)


DEFAULT_ADDRESS_CANDIDATES: Final[tuple[str, ...]] = _generate_address_candidates()
"""Every `_STREET_NAMES` x `_CITY_STATES` combination — 5,040
candidates. Uniqueness comes from the (street, city_state) pair alone;
the house number is cosmetic and may repeat across different pairs."""
