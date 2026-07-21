"""A placeholder finite candidate list for Tier-2 name-surrogate
allocation.

Deliberately small and explicitly a placeholder — **not** the
production list Phase 4 will need once real PERSON/ORG/ADDRESS
detection exists and starts calling `Session.allocate_or_lookup_name()`
for real. Sized only to exercise the allocator's own collision and
exhaustion mechanics in Phase 3 Task 2's tests (BUILD.md, Phase 3:
"Test with a forced-tiny name list to make collisions certain").

Sourcing a properly-sized (~5,000 names, per ARCHITECTURE.md's own
collision-math illustration), responsibly-curated production list —
and deciding whether one list serves PERSON/ORG/ADDRESS alike or each
needs its own — is explicitly deferred to whenever Phase 4 wires real
Tier-2 detection to this allocator. Using this list for anything beyond
Phase 3's own mechanics tests would be premature.
"""

from typing import Final

DEFAULT_NAME_CANDIDATES: Final[tuple[str, ...]] = (
    "Aarav Sharma",
    "Vivaan Gupta",
    "Aditya Verma",
    "Vihaan Reddy",
    "Arjun Nair",
    "Sai Iyer",
    "Reyansh Rao",
    "Krishna Menon",
    "Ishaan Pillai",
    "Rohan Kapoor",
    "Ananya Joshi",
    "Diya Patel",
    "Saanvi Desai",
    "Aadhya Shah",
    "Kiara Mehta",
    "Myra Chaudhary",
    "Anika Bose",
    "Navya Chatterjee",
    "Pari Mukherjee",
    "Riya Banerjee",
    "Kabir Malhotra",
    "Advik Sinha",
    "Vivan Chopra",
    "Atharv Bhatt",
    "Ayaan Trivedi",
    "Yash Choudhary",
    "Dhruv Agarwal",
    "Karthik Subramaniam",
    "Rahul Krishnan",
    "Siddharth Rajan",
    "Meera Ramesh",
    "Priya Venkatesh",
    "Neha Krishnamurthy",
    "Pooja Balasubramaniam",
    "Kavya Narayanan",
    "Tanvi Raghavan",
    "Ishita Sundaram",
    "Aisha Pillai",
    "Zara Khan",
    "Fatima Sheikh",
)
"""40 synthetic Indian-name-shaped placeholders — enough to force
collisions and exhaustion in a small test fixture, nowhere near enough
for real Tier-2 traffic. See the module docstring."""
